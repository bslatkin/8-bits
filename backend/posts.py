#!/usr/bin/env python
#
# Copyright 2010 Brett Slatkin, Nathan Naze
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Posts and sequencing."""

import datetime
import json
import logging

from google.appengine.api import api_base_pb
from google.appengine.api import apiproxy_stub_map
from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.api.channel import channel
from google.appengine.api.channel import channel_service_pb
from google.appengine.runtime import apiproxy_errors

# Local libs
import base
import config
import models
import ndb
import presence


def dirty_bit(shard, set=False, check=False, clear=False):
    """Sets or checks the dirty bit for a shard."""
    assert set ^ check ^ clear
    key = 'dirty-bit-shard-%s' % shard
    if set:
        memcache.set(key, 1)
    elif clear:
        memcache.delete(key)
    else:
        return bool(memcache.get(key))


@ndb.tasklet
def enqueue_apply_task(shard, post_id=None):
    """Enqueues a push task to apply new Posts to be sequenced.

    Args:
        shard: Shard to submit an apply task for.
        post_id: Optional. Indicates to the apply task which posts it should
            apply at the very least. This lets us handle the race condition
            where a pull task is enqueued, then the apply task runs, the apply
            task queries for pull tasks, finds none, and gives up, leaving the
            pull task around.
    """
    join_index = 1
    shard_record = yield models.Shard.get_by_id_async(
        shard, use_cache=False, use_memcache=False)
    if shard_record:
        logging.debug(
            'Adding apply task for shard=%r with sequence_number=%r',
            shard, shard_record.sequence_number)
        join_index = shard_record.sequence_number

    if post_id is None:
        post_id = ''

    for i in xrange(3):
        try:
            taskqueue.Task(
                url='/work/apply_posts',
                params=dict(shard=shard, post_id=post_id),
                name='apply-%s-join-%s' % (shard, join_index),
                countdown=1
            ).add(config.apply_queue)
        except (taskqueue.TombstonedTaskError,
                taskqueue.TaskAlreadyExistsError):
            logging.debug(
                'Enqueued apply task for shard=%r but task already present',
                shard)
        except:
            # Retry on any intermittent failure.
            continue
        break


def enqueue_post_task(shard, post_ids, new_topic=None):
    """Enqueues a task to post a new task on a shard."""
    params_dict = dict(shard=shard, post_ids=post_ids)
    if new_topic is not None:
        params_dict.update(new_topic=new_topic)

    taskqueue.Task(
        method='PULL',
        tag=str(shard),
        params=params_dict,
    ).add(config.pending_queue, transactional=ndb.in_transaction())


def insert_post(shard, **kwargs):
    """Inserts a post at the present time, returning its key.

    If the post_id keyword argument is not supplied, a new post ID will be
    auto assigned.
    """
    # Create the posting and insert it.
    post_id = kwargs.pop('post_id', None)
    if not post_id:
        post_id = models.human_uuid()

    new_topic = kwargs.get('new_topic', None)

    kwargs['post_time'] = datetime.datetime.now()

    post_key = ndb.Key(models.Post._get_kind(), post_id)
    post = models.Post(
        key=post_key,
        **kwargs)

    @ndb.tasklet
    def txn():
        if (yield post_key.get_async(use_memcache=False, use_cache=False)):
            logging.warning('Post already exists for shard=%r, post_id=%r',
                            shard, post_id)
            raise ndb.Rollback()

        yield post.put_async(use_memcache=False, use_cache=False)

        # Pull task that indicates the post to apply. This must encode the
        # new_topic data for this post so the apply_posts() function doesn't
        # need the models.Post entity in order to make progress.
        enqueue_post_task(shard, [post_id], new_topic=new_topic)

    # Notify all users of the post.
    futures = []
    futures.append(ndb.transaction_async(txn))
    futures.append(notify_posts(shard, [post]))

    # Set the dirty bit for this shard. This causes apply_posts to run a
    # second time if the Post transaction above completed while apply_posts
    # was already in flight.
    dirty_bit(shard, set=True)

    # Enqueue an apply task to sequence and notify the new post.
    futures.append(enqueue_apply_task(shard, post_id=post_id))

    # Wait on futures in case they raise errors.
    ndb.Future.wait_all(futures)

    return post_key


def apply_posts(shard=None,
                insertion_post_id=None,
                lease_seconds=10,
                max_tasks=20):
    """Applies a set of pending posts to a shard.

    If shard is None then this function will apply mods for whatever is the
    first shard it can find in the pull task queue.

    insertion_post_id is the post_id that first caused this apply task to be
    enqueued. This task will retry until it applies the insertion_post_id
    itself or it can confirm that the insertion_post_id has already been
    applied. insertion_post_id may be empty if the apply task is not associated
    with a particular post (such as cronjobs/cleanup tasks).
    """
    # Do not use caching for NDB in this task queue worker.
    ctx = ndb.get_context()
    ctx.set_cache_policy(lambda x: False)
    ctx.set_memcache_policy(lambda x: False)

    # Fetch the new Posts to put in sequence.
    queue = taskqueue.Queue(config.pending_queue)

    # When no shard is specified, process the first tag we find.
    task_list = []
    if not shard:
        task_list.extend(queue.lease_tasks(lease_seconds, 1))
        if not task_list:
            logging.debug('apply_posts with no specific shard found no tasks')
            return
        params = task_list[0].extract_params()
        shard = params['shard']
        logging.debug('apply_posts with no specific shard found shard=%r',
                      shard)

    # Clear the dirty bit on this shard to start the time horizon.
    dirty_bit(shard, clear=True)

    # Find tasks pending for the current shard.
    task_list.extend(
        queue.lease_tasks_by_tag(lease_seconds, max_tasks, tag=str(shard)))

    receipt_key_list = []
    new_topic = None
    for task in task_list:
        params = task.extract_params()

        # Extract the new topic shard associated with this task, if any. The
        # last one wins. If all of the found posts have already been applied,
        # then topic assignment will be ignored.
        new_topic = params.get('new_topic') or new_topic

        post_id_list = params.get('post_ids')
        if post_id_list is None:
            # This may happen on replica shards if it turns out there are no
            # unapplied post IDs but an apply task still ran.
            post_id_list = []
        elif not isinstance(post_id_list, list):
            post_id_list = [post_id_list]

        for post_id in post_id_list:
            receipt_key = ndb.Key(
                models.Post._get_kind(), post_id,
                models.Receipt._get_kind(), shard)
            receipt_key_list.append(receipt_key)

    receipt_list = ndb.get_multi(receipt_key_list)

    # Some tasks may be in the pull queue that were already put in sequence.
    # So ignore these and only apply the new ones.
    unapplied_receipts = [
        models.Receipt(key=k)
        for k, r in zip(receipt_key_list, receipt_list)
        if r is None]
    unapplied_post_ids = [r.post_id for r in unapplied_receipts]

    # Double check if we think there should be work to apply but we didn't find
    # any. This will force the apply task to retry immediately if the post task
    # was not found. This can happen when the pull queue's consistency is
    # behind.
    if not unapplied_receipts and insertion_post_id:
        receipt_key = ndb.Key(
            models.Post._get_kind(), insertion_post_id,
            models.Receipt._get_kind(), shard)
        receipt = receipt_key.get()
        if receipt:
            logging.warning(
                'No post application to do for shard=%r, but post_id=%r '
                'already applied; doing nothing in this task',
                shard, insertion_post_id)
            new_topic = None
            # Do not 'return' here. We need to increment the shard sequence or
            # else tasks will not run for this shard in the future because of
            # de-duping.
        else:
            raise base.Error('No post application to do for shard=%r, but'
                             'post_id=%r has not been applied; will retry' %
                             (shard, insertion_post_id))

    now = datetime.datetime.now()

    def txn():
        shard_record = models.Shard.get_by_id(shard)
        # TODO(bslatkin): Just drop this task entirely if the shard cannot
        # be found. Could happen for old shards that were cleaned up.
        assert shard_record

        # One of the tasks in this batch has a topic assignment. Apply it here.
        if new_topic:
            logging.debug('Changing topic from %r to %r',
                          shard_record.current_topic, new_topic)
            shard_record.current_topic = new_topic
            shard_record.topic_change_time = now

        new_sequence_numbers = list(xrange(
            shard_record.sequence_number,
            shard_record.sequence_number + len(unapplied_receipts)))
        shard_record.sequence_number += max(1, len(unapplied_receipts))

        # Write post references that point at the newly sequenced posts.
        to_put = [shard_record]
        for receipt, sequence in zip(unapplied_receipts, new_sequence_numbers):
            to_put.append(models.PostReference(
                id=sequence,
                parent=shard_record.key,
                post_id=receipt.post_id))
            # Update the receipt entity here; it will be written outside this
            # transaction, since these receipts may span multiple entity
            # groups.
            receipt.sequence = sequence

        # Enqueue replica posts transactionally, to make sure everything
        # definitely will get copied over to the replica shard.
        if shard_record.current_topic:
            enqueue_post_task(shard_record.current_topic, unapplied_post_ids)

        ndb.put_multi(to_put)

        return shard_record, new_sequence_numbers

    # Have this only attempt a transaction a single time. If the transaction
    # fails the task queue will retry this task within 4 seconds. Because
    # apply tasks are always named by the current Shard.sequence_number we
    # can be reasonably sure that no other apply task for this shard will be
    # running concurrently when this fails.
    shard_record, new_sequence_numbers = ndb.transaction(txn, retries=1)
    replica_shard = shard_record.current_topic

    logging.debug('Applied %d posts for shard=%r, sequence_numbers=%r',
                  len(unapplied_receipts), shard, new_sequence_numbers)

    futures = []

    # Save receipts for all the posts.
    futures.extend(ndb.put_multi_async(unapplied_receipts))

    # Notify all logged in users of the new posts.
    futures.append(notify_posts(
        shard, unapplied_post_ids, sequence_numbers=new_sequence_numbers))

    # Replicate posts to a topic shard.
    if replica_shard:
        logging.debug('Replicating source shard=%r to replica shard=%r',
                      shard, replica_shard)
        futures.append(enqueue_apply_task(replica_shard))

    # Success! Delete the tasks from this queue.
    queue.delete_tasks(task_list)

    # Always run one more apply task to clean up any posts that came in
    # while this transaction was processing.
    if dirty_bit(shard, check=True):
        futures.append(enqueue_apply_task(shard))

    # Wait on all pending futures in case they raise errors.
    ndb.Future.wait_all(futures)

    # For root shards, add shard cleanup task to check for user presence and
    # cause notification of user logouts if the channel API did not detect the
    # user closing the connection.
    if not shard_record.root_shard:
        presence.enqueue_cleanup_task(shard)


def marshal_posts(shard, post_list):
    """Organizes a list of posts into a JSON-serializable list."""
    out = []
    for post in post_list:
        post_dict = dict(
            shardId=shard,
            archiveType=models.Post.ARCHIVE_REVERSE_MAPPING[post.archive_type],
            nickname=post.nickname,
            title=post.title,
            body=post.body,
            postTimeMs=models.datetime_to_stamp_ms(post.post_time),
            sequenceId=getattr(post, 'sequence', None),
            newTopicId=post.new_topic,
            postId=post.post_id)
        out.append(post_dict)
    return out


@ndb.tasklet
def send_message_async(client_id, message):
    """Send a message to a channel asynchronously.

    Based off of App Engine's channel.send_message function.
    """
    if isinstance(message, unicode):
        message = message.encode('utf-8')

    request = channel_service_pb.SendMessageRequest()
    response = api_base_pb.VoidProto()
    request.set_application_key(client_id)
    request.set_message(message)

    rpc = apiproxy_stub_map.UserRPC(channel._GetService())
    rpc.make_call('SendChannelMessage', request, response)
    yield rpc
    try:
        raise ndb.Return(rpc.get_result())
    except apiproxy_errors.ApplicationError, e:
        raise channel._ToChannelError(e)


@ndb.tasklet
def notify_posts(shard, post_list, sequence_numbers=None):
    """Notifies logged-in users of a set of new posts.

    Args:
        shard: Shard ID to notify for.
        post_list: When the post_list is a list of strings, then it's assumed
            these are the IDs of Posts that must be fetched prior to
            notification. Otherwise these should be Post entities.
        sequence_numbers: When supplied, should be a list of sequence numbers
            that correspond to each of the items in the post_list, in order.
            This is used to tell the user what the sequence ID of each post is
            within a particular shard.
    """
    if not post_list:
        return

    if isinstance(post_list[0], basestring):
        post_keys = [ndb.Key(models.Post._get_kind(), post_id)
                     for post_id in post_list]
        post_list = yield ndb.get_multi_async(post_keys)

    if not sequence_numbers:
        sequence_numbers = [None] * len(post_list)

    for post, sequence in zip(post_list, sequence_numbers):
        post.sequence = sequence

    posts_json = json.dumps({
        'posts': marshal_posts(shard, post_list),
    })

    login_record_list = presence.get_present_users(shard)
    rpc_list = []
    for login_record in login_record_list:
        logging.debug(
            'Informing shard=%r, user=%r, nickname=%r about messages '
            'with sequence_numbers=%r', shard, login_record.user_id,
            login_record.nickname, sequence_numbers)
        browser_token = presence.get_token(login_record.user_id)
        rpc_list.append(send_message_async(browser_token, posts_json))

    for rpc in rpc_list:
        try:
            yield rpc
        except channel.Error, e:
            # NOTE: When receiving an InvalidChannelKeyError the message may
            # still be available the next time the user connects to the channel
            # with that same application key due to buffering in the backends.
            # The dev_appserver mimics this behavior, but it's not reliable in
            # prod.
            logging.warning('Could not send JSON message to user=%r with '
                            'browser_token=%r. %s: %s', login_record.user_id,
                            browser_token, e.__class__.__name__, str(e))


class ApplyWorker(base.BaseHandler):
    """Applies pending posts."""

    def post(self):
        shard = self.request.get('shard')
        post_id = self.request.get('post_id')
        apply_posts(shard=shard, insertion_post_id=post_id)

    def get(self):
        apply_posts()


class PostHandler(base.BaseRpcHandler):
    """Handles users making new posts."""

    require_shard = True

    def handle(self):
        archive_type = self.get_required('type', str)
        archive_enum = models.Post.ARCHIVE_MAPPING.get(archive_type)
        if archive_enum not in models.Post.ALLOWED_ARCHIVES:
            raise base.BadParameterValueError(
                '"%s" is not a valid post type' % archive_type)

        body = self.get_required('body', unicode, html_escape=True)
        post_id = self.get_required('post_id', str)

        new_topic = self.get_required('new_topic', str, '')
        if archive_enum != models.Post.TOPIC_CHANGE:
            new_topic = None

        login_record = self.require_active_login()

        post_key = insert_post(
            self.shard,
            post_id=post_id,
            archive_type=archive_enum,
            nickname=login_record.nickname,
            user_id=login_record.user_id,
            body=body,
            new_topic=new_topic)
        self.json_response['postId'] = post_key.id()


class ListPostsHandler(base.BaseRpcHandler):
    """Handles retrieving posts for a shard.

    If start and end are not supplied, then the most recent posts are fetched.
    If only end is supplied, then the last 'count' posts including that
    sequence number will be fetched. Other combinations of start/end
    will not work.

    Args:
        start: Sequence number to start searching. Inclusive.
        end: Sequence number to stop searching. Inclusive.
        count: How many posts to fetch. Defaults to 100.

    Returns:
        posts: List of marshaled posts.
    """

    require_shard = True

    def handle(self):
        start = self.get_required('start', int, 0)
        end = self.get_required('end', int, 0)
        count = self.get_required('count', int, 100)

        query = models.PostReference.query()

        if not start and not end:
            # Get newest posts by doing a prefix scan.
            start_key = ndb.Key(
                models.Shard._get_kind(), self.shard,
                models.PostReference._get_kind(), 1)
            end_key = ndb.Key(
                models.Shard._get_kind(), self.shard,
                models.PostReference._get_kind(), 2**62)
        elif not start and end:
            # Get a specific set of posts
            start_key = ndb.Key(
                models.Shard._get_kind(), self.shard,
                models.PostReference._get_kind(), max(1, end - count))
            end_key = ndb.Key(
                models.Shard._get_kind(), self.shard,
                models.PostReference._get_kind(), end)
        else:
            # Should not happen
            assert False

        query = query.filter(models.PostReference.key >= start_key)
        query = query.filter(models.PostReference.key <= end_key)
        query = query.order(-models.PostReference.key)

        ref_list = query.fetch(count)
        post_kind = models.Post._get_kind()

        post_key_list = [ndb.Key(post_kind, ref.post_id) for ref in ref_list]
        post_list = ndb.get_multi(post_key_list)
        adjusted_post_list = []
        for post, ref in zip(post_list, ref_list):
            # PostReference entities may point to non-existent Post entities
            # once the cleanup job has run. Filter them out here. The client
            # side won't try to scan for posts previous to the last one that's
            # actually found, so this filtering is okay.
            if not post:
                continue

            # TODO(bslatkin): Drop post entities that are older than
            # config.ephemeral_lifetime_seconds, in case the background job
            # takes longer than expected to delete things.

            post.sequence = ref.sequence
            adjusted_post_list.append(post)

        self.json_response['posts'] = marshal_posts(
            self.shard, adjusted_post_list)


ROUTES = [
    (r'/rpc/list_posts', ListPostsHandler),
    (r'/rpc/post', PostHandler),
    (r'/work/apply_posts', ApplyWorker),
]
