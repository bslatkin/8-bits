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

"""Primary user-facing functionality of the 8-bits chat system."""

import base64
import cgi
import datetime
import hashlib
import json
import logging
import os
import time
import traceback
import uuid
import wsgiref.handlers
import xml.sax.saxutils

from google.appengine.api import api_base_pb
from google.appengine.api import apiproxy_stub_map
from google.appengine.api.channel import channel
from google.appengine.api.channel import channel_service_pb
from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext.appstats import recording
from google.appengine.ext import blobstore
from google.appengine.ext import webapp
from google.appengine.ext.webapp import blobstore_handlers
from google.appengine.ext.webapp import template
from google.appengine.runtime import apiproxy_errors

# Local libs
from beaker import middleware
import config
import models
import ndb

################################################################################

class Error(Exception):
  """Base class for exceptions."""

class MissingParameterError(Error):
  """A required parameter was missing."""

class BadParameterValueError(Error):
  """A parameter has a bad type."""

class NotAuthorizedError(Error):
  """The user is not authorized to do this action."""

class TopicShardError(Error):
  """Topic shards cannot be used in this way."""

class PostError(Error):
  """A posting could not be made."""

################################################################################
# Utility classes, functions.

# TODO(bslatkin): Add XSRF protection to this class.
class BaseHandler(webapp.RequestHandler):
  """Base handler for handling web requests."""

  # Allow requests with the GET verb.
  get_enabled = True

  # Allow requests with the POST verb.
  post_enabled = True

  def get(self, *args):
    if not self.get_enabled:
      self.response.set_status(405)
      return
    self.session = self.request.environ['beaker.session']
    self.handle_request(*args)

  def post(self, *args):
    if not self.post_enabled:
      self.response.set_status(405)
      return
    self.session = self.request.environ['beaker.session']
    self.handle_request(*args)

  def handle_request(self, *args):
    raise NotImplementedError()

  def get_required(self,
                   name,
                   type_constructor,
                   default=None,
                   repeated=False,
                   html_escape=False):
    """Retrieves a required parameter with the given name and default."""
    value_list = self.request.get_all(name)

    if default is None and not value_list:
      raise MissingParameterError('Parameter "%s" is required' % name)
    else:
      value_list.append(default)

    out_list = []
    for value in value_list:
      try:
        value = type_constructor(value)
      except ValueError:
        raise BadParameterValueError('Parameter "%s" has an invalid value: %r'
                                     % (name, value))

      if html_escape:
        value = cgi.escape(value)

      out_list.append(value)

    if repeated:
      return out_list
    return out_list[0]

  def require_active_login(self):
    """Raises an error if the user does not have an active connection."""
    login_record = models.LoginRecord.get_by_id(self.user_id)
    if not only_active_users(login_record):
        raise NotAuthorizedError('Connection no longer valid, must relogin')
    return login_record

  def render(self, template_name, context=None):
    """Renders the given template and context."""
    js_mode = 'compiled'
    if config.debug and config.is_dev_appserver:
      js_mode = self.request.get('js_mode', 'raw')

    my_context = {
      'cache_buster': config.version_id,
      'host_url': self.request.host_url,
      'js_mode': js_mode,
    }
    if context:
      my_context.update(context)

    self.response.out.write(
      template.render('templates/' + template_name, my_context))


class BaseRpcHandler(BaseHandler):
  """Base handler for turning responses into JSON.

  Sub-classes should override the handle() method and stuff their response
  parameters into self.json_response. In the event an exception is raised
  it will be returned to the caller as 'error_class' and 'error_detail'
  parameters in the JSON response with a 500 response. In the successful case
  the response will be JSON with a 200 response.

  Properties:
    - all_shards: List of all shards this user is logged into.
    - shard: The current logged in shard, set when 'require_shard' is True.
  """

  # By default RPCs are post only.
  get_enabled = False

  # Whether or not to require user log-in to the shard they assert.
  require_shard = False

  # Do not write the output JSON or content-type to the response.
  raw_response = False  # TODO(bslatkin): Refactor this to use BaseHandler

  def handle_request(self, *args):
    self.session = self.request.environ['beaker.session']
    if 'shards' in self.session:
      self.all_shards = self.session['shards']
    else:
      self.all_shards = []
    if self.require_shard:
      self.shard = self._verify_shard_login()
      self.user_id = self.all_shards[self.shard]
    else:
      self.shard = None
      self.user_id = None

    self.json_response = {}
    try:
      self.handle(*args)
    except Exception, e:
      logging.exception('Error encountered during RPC')
      self.json_response['errorClass'] = e.__class__.__name__
      self.json_response['errorDetail'] = str(e)
      self.json_response['errorTraceback'] = traceback.format_exc()
      self.response.set_status(500)
    finally:
      if not self.raw_response:
        self.response.headers['Content-Type'] = 'text/javascript'
        self.response.out.write(json.dumps(self.json_response))

  def handle(self):
    raise NotImplementedError('Override in sub-class')

  def _verify_shard_login(self):
    """Verifies the user is logged into the shard they assert, return it."""
    shard = self.get_required('shard', str)
    if 'shards' not in self.session:
      raise NotAuthorizedError('Your cookie has no valid shards')
    if shard not in self.session['shards']:
      raise NotAuthorizedError('You may not access shard %s' % shard)
    return shard


def human_uuid():
  """Generates a more human friendly UUID."""
  return base64.b32encode(uuid.uuid4().bytes).strip('=').lower()


################################################################################
# Posts and sequencing

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
      apply at the very least. This lets us handle the race condition where
      a pull task is enqueued, then the apply task runs, the apply task queries
      for pull tasks, finds none, and gives up, leaving the pull task around.
  """
  join_index = 1
  shard_record = yield models.Shard.get_by_id_async(
      shard, use_cache=False, use_memcache=False)
  if shard_record:
    logging.debug('Adding apply task for shard=%r with sequence_number=%r',
                  shard, shard_record.sequence_number)
    join_index = shard_record.sequence_number

  if post_id is None:
    post_id = ''

  try:
    taskqueue.Task(
      url='/work/apply_posts',
      params=dict(shard=shard, post_id=post_id),
      name='apply-%s-join-%s' % (shard, join_index),
      countdown=1
    ).add(config.apply_queue)
  except (taskqueue.TombstonedTaskError, taskqueue.TaskAlreadyExistsError):
    logging.debug('Enqueued apply task for shard=%r but task already present',
                  shard)


def enqueue_cleanup_task(shard):
  """Enqueues a task to invoke the ShardCleanupHandler periodically."""
  try:
    taskqueue.Task(
      url='/work/cleanup',
      params=dict(shard=shard),
      name='cleanup-%s-time-%d' % (
          shard, time.time() / config.shard_cleanup_period_seconds),
      countdown=config.shard_cleanup_period_seconds
    ).add(config.cleanup_queue)
  except (taskqueue.TombstonedTaskError, taskqueue.TaskAlreadyExistsError):
    logging.debug('Enqueued cleanup task for shard=%r but task already present',
                  shard)


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
    post_id = human_uuid()

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
  enqueued. This task will retry until it applies the insertion_post_id itself
  or it can confirm that the insertion_post_id has already been applied.
  insertion_post_id may be empty if the apply task is not associated with
  a particular post (such as cronjobs/cleanup tasks).
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
    logging.debug('apply_posts with no specific shard found shard=%r', shard)

  # Clear the dirty bit on this shard to start the time horizon.
  dirty_bit(shard, clear=True)

  # Find tasks pending for the current shard.
  task_list.extend(
      queue.lease_tasks_by_tag(lease_seconds, max_tasks, tag=str(shard)))

  receipt_key_list = []
  new_topic = None
  for task in task_list:
    params = task.extract_params()

    # Extract the new topic shard associated with this task, if any. The last
    # one wins. If all of the found posts have already been applied, then topic
    # assignment will be ignored.
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

  # Double check if we think there should be work to apply but we didn't
  # find any. This will force the apply task to retry immediately if the
  # post task was not found. This can happen when the pull queue's consistency
  # is behind.
  if not unapplied_receipts and insertion_post_id:
    receipt_key = ndb.Key(
        models.Post._get_kind(), insertion_post_id,
        models.Receipt._get_kind(), shard)
    receipt = receipt_key.get()
    if receipt:
      logging.warning('No post application to do for shard=%r, but post_id=%r '
                      'already applied; doing nothing in this task',
                      shard, insertion_post_id)
      new_topic = None
      # Do not 'return' here. We need to increment the shard sequence or else
      # tasks will not run for this shard in the future because of de-duping.
    else:
      raise Error('No post application to do for shard=%r, but'
                  'post_id=%r has not been applied; will retry' %
                  (shard, insertion_post_id))

  now = datetime.datetime.now()

  def txn():
    shard_record = models.Shard.get_by_id(shard)
    # TODO(bslatkin): Just drop this task entirely if this happens
    assert shard_record

    # One of the tasks in this batch has a topic assignment. Apply it here.
    if new_topic:
      logging.debug('Changing topic from %r to %r',
                    shard_record.current_topic, new_topic)
      shard_record.current_topic = new_topic
      shard_record.topic_change_time = now

    new_sequence_numbers = list(
        xrange(shard_record.sequence_number,
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
      # transaction, since these receipts may span multiple entity groups.
      receipt.sequence = sequence

    # Enqueue replica posts transactionally, to make sure everything definitely
    # will get copied over to the replica shard.
    if shard_record.current_topic:
      enqueue_post_task(shard_record.current_topic, unapplied_post_ids)

    ndb.put_multi(to_put)

    return shard_record.current_topic, new_sequence_numbers

  # Have this only attempt a transaction a single time. If the transaction
  # fails the task queue will retry this task within 4 seconds. Because
  # apply tasks are always named by the current Shard.sequence_number we
  # can be reasonably sure that no other apply task for this shard will be
  # running concurrently when this fails.
  replica_shard, new_sequence_numbers = ndb.transaction(txn, retries=1)

  logging.debug('Applied %d posts for shard=%r, sequence_numbers=%r',
                len(unapplied_receipts), shard, new_sequence_numbers)

  futures = []

  # Save receipts for all the posts.
  futures.extend(ndb.put_multi_async(unapplied_receipts))

  # Notify all logged in users of the new posts.
  futures.append(notify_posts(shard, unapplied_post_ids,
                              sequence_numbers=new_sequence_numbers))

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

  # Add shard cleanup task to check for user presence and cause notification
  # of user logouts if the channel API did not detect the user closing the
  # connection.
  enqueue_cleanup_task(shard)


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
    post_list: When the post_list is a list of strings, then it's assumed these
      are the IDs of Posts that must be fetched prior to notification.
      Otherwise these should be Post entities.
    sequence_numbers: When supplied, should be a list of sequence numbers
      that correspond to each of the items in the post_list, in order. This
      is used to tell the user what the sequence ID of each post is within
      a particular shard.
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

  login_record_list = get_present_users(shard)
  rpc_list = []
  for login_record in login_record_list:
    logging.debug('Informing shard=%r, user=%r, nickname=%r about messages '
                  'with sequence_numbers=%r', shard, login_record.user_id,
                  login_record.nickname, sequence_numbers)
    browser_token = get_token(login_record.user_id)
    rpc_list.append(send_message_async(browser_token, posts_json))

  for rpc in rpc_list:
    try:
      yield rpc
    except channel.Error, e:
      # NOTE: When receiving an InvalidChannelKeyError the message may still
      # be available the next time the user connects to the channel with that
      # same application key due to buffering in the backends. The
      # dev_appserver mimics this behavior, but it's not reliable in prod.
      logging.warning('Could not send JSON message to user=%r with '
                      'browser_token=%r. %s: %s', login_record.user_id,
                      browser_token, e.__class__.__name__, str(e))

################################################################################
# User login and presence

def invalidate_user_cache(shard):
  """Invalidates the present user cache for the given shard."""
  shard_key = 'users-shard-%s' % shard
  memcache.delete(shard_key)
  # TODO(bslatkin): Consider refilling the cache in a background task.


def marshal_users(user_list):
  """Organizes a list of LoginRecords into a JSON-serializable list."""
  if not user_list:
    return 'Nobody else is here'

  # Sort users present the shortest time first.
  user_list.sort(key=lambda u: u.last_update_time, reverse=True)
  nicknames = [u.nickname for u in user_list]

  if len(user_list) == 1:
    return '%s is here too' % nicknames[0]

  if len(user_list) == 2:
    return '%s and %s are here too' % (nicknames[0], nicknames[1])

  return '%s, and %s are here too' % (
      ', '.join(nicknames[:-1]),
      nicknames[-1])


def only_active_users(*login_record_list):
  """Filters a list of users to only be those that are actually active."""
  now = datetime.datetime.now()
  oldest_time = (
      now - datetime.timedelta(seconds=config.user_max_inactive_seconds))

  result_list = []
  for login_record in login_record_list:
    if not login_record.online:
      logging.debug('User is no longer online: %r', login_record)
      continue

    if (not login_record.last_update_time or
        login_record.last_update_time < oldest_time):
      logging.debug('User update time too far in past: %r', login_record)
      continue

    result_list.append(login_record)

  return result_list


def maybe_update_token(login_record, force=False):
  """Assigns the user a new channel token if needed.

  Args:
    login_record: Record for the user.
    force: Optional. When True, always update the user's token. This is used
      when the token is known to be bad on the client side.

  Returns:
    True if a new token was issued.
  """
  now = datetime.datetime.now()
  oldest_token_time = (
      now - datetime.timedelta(seconds=config.user_token_lifetime_seconds))

  if not force and (
      login_record.browser_token_issue_time and
      login_record.browser_token_issue_time > oldest_token_time):
    return False

  login_record.browser_token = channel.create_channel(
      get_token(login_record.user_id),
      5 + config.user_token_lifetime_seconds // 60)  # 5 minutes of wiggle room
  login_record.browser_token_issue_time = now
  return True


def get_present_users(shard, include_stale=False):
  """Returns a list of present users for a shard in descending log-in order.

  Notably, this query is going to be eventually consistent and miss the folks
  who have just recently joined. That's okay. It's like they joined the chat
  a little bit late. They will still be able to see previous Posts through
  historical queries.
  """
  shard_key = 'users-shard-%s' % shard
  user_list = memcache.get(shard_key)
  if user_list:
    return user_list

  user_list = (models.LoginRecord.query()
      .filter(models.LoginRecord.shard_id == shard)
      .filter(models.LoginRecord.online == True)
      .order(-models.LoginRecord.last_update_time)
      .fetch(1000))

  if not include_stale:
    # Only cache this query for the case where we're pruning stale users.
    user_list = only_active_users(*user_list)
    memcache.set(shard_key, user_list, config.user_max_inactive_seconds)

  return user_list


def user_logged_in(shard, user_id):
  """Logs in a user to a shard. Always returns the current user ID."""
  login_record = None
  if user_id:
    # Re-login the user if they somehow lost their browser state and
    # needed to reload the page. This assumes the cookie was okay.
    login_record = models.LoginRecord.get_by_id(user_id)
    if login_record and not login_record.online:
      def txn():
        login_record = models.LoginRecord.get_by_id(user_id)
        assert login_record
        login_record.online = True
        login_record.put()

      logging.debug('Re-logging-in user_id=%r to shard=%r',
                    login_record.user_id, shard)
      ndb.transaction(txn)

  # User is logging in for the first time or somehow state was deleted.
  if not login_record:
    login_record = models.LoginRecord(
      key=ndb.Key(models.LoginRecord._get_kind(), human_uuid()),
      shard_id=shard,
      online=True)
    login_record.put()
    logging.debug('Logged-in new user_id=%r to shard=%r',
                  login_record.user_id, shard)

  invalidate_user_cache(shard)
  return login_record.user_id


def user_logged_out(shard, user_id):
  """Notifies other users that the given user has logged out of a shard."""
  def txn():
    login_record = models.LoginRecord.get_by_id(user_id)
    if not login_record:
        raise ndb.Rollback()
    login_record.online = False
    login_record.put()
    return login_record

  login_record = ndb.transaction(txn)

  if not login_record:
    logging.warning('Tried to log out user_id=%r from shard=%r, '
                    'but LoginRecord did not exist', user_id, shard)
    return

  insert_post(
      shard,
      archive_type=models.Post.USER_LOGOUT,
      nickname=login_record.nickname,
      user_id=user_id,
      body='%s has left' % login_record.nickname)

  invalidate_user_cache(shard)
  logging.debug('Logged out user_id=%r from shard=%r', user_id, shard)


def get_token(user_id):
  """Gets the channel token for the given user."""
  return user_id

################################################################################
# Workers

class ApplyWorker(BaseHandler):
  """Applies pending posts."""

  def post(self):
    shard = self.request.get('shard')
    post_id = self.request.get('post_id')
    apply_posts(shard=shard, insertion_post_id=post_id)

  def get(self):
    apply_posts()


class ShardCleanupHandler(BaseHandler):
  """Handles periodic cleanup requests for a specific shard.

  This handler will run periodically (~minute) for all shards that have
  active participants. It's meant to do state cleanup for the shard, such as
  forcing logouts for users who have not heartbeated in N seconds.
  """

  def post(self):
    shard = self.get_required('shard', str)

    all_users_list = get_present_users(shard, include_stale=True)
    active_users_list = only_active_users(*all_users_list)

    all_users_set = set(u.user_id for u in all_users_list)
    active_users_set = set(u.user_id for u in active_users_list)

    for user_id in (all_users_set - active_users_set):
      user_logged_out(shard, user_id)

    # As long as there are still active users, continue to try to
    # clean them up.
    if active_users_set:
      enqueue_cleanup_task(shard)

################################################################################
# RPC handlers

class PresenceHandler(BaseRpcHandler):
  """Handles updating user presence."""

  def handle(self):
    shard = self.get_required('shard', str)
    nickname = self.get_required('nickname', unicode, '', html_escape=True)
    accepted_terms = self.get_required('accepted_terms', str, '') == 'true'
    sounds_enabled = self.get_required('sounds_enabled', str, '') == 'true'
    retrying = self.get_required('retrying', str, '') == 'true'

    # Make sure this shard can be logged into.
    shard_record = models.Shard.get_by_id(shard)
    if shard_record.root_shard:
      raise TopicShardError('Cannot login to topic shard')

    if 'shards' not in self.session:
      # First login on any shard with no cookie present.
      self.session['shards'] = {}

    user_id = self.session['shards'].get(shard)
    if not user_id:
      # First login to this shard.
      user_id = human_uuid()
      self.session['shards'][shard] = user_id

    def txn():
      last_nickname = None
      user_connected = True

      login = models.LoginRecord.get_by_id(user_id)
      if not login:
        login = models.LoginRecord(
          key=ndb.Key(models.LoginRecord._get_kind(), user_id),
          shard_id=shard)
      elif only_active_users(login):
        # This is a heartbeat presence check
        user_connected = False

      if maybe_update_token(login, force=retrying):
        logging.debug('Issuing channel token: user_id=%r, shard=%r, force=%r',
                      user_id, shard, retrying)

      if nickname:
        # This is a potential nickname change. Right now the client always
        # sends the nickname on every request, so we need to check for the
        # difference to detect a rename.
        last_nickname = login.nickname
        login.nickname = nickname

      if accepted_terms:
        # This is a ToS acceptance
        login.accepted_terms_version = config.terms_version

      login.online = True
      login.sounds_enabled = sounds_enabled
      login.put()

      return last_nickname, user_connected, login.browser_token

    last_nickname, user_connected, browser_token = ndb.transaction(txn)

    # Invalidate the cache so the nickname will be updated next time
    # someone requests the roster.
    invalidate_user_cache(shard)

    message = None
    archive_type = None

    if nickname and last_nickname and last_nickname != nickname:
      message = '%s has changed their nickname to %s' % (
          last_nickname, nickname)
      archive_type = models.Post.USER_UPDATE
      logging.debug('User update user_id=%r, shard=%r', user_id, shard)
    elif user_connected:
      message = '%s has joined' % nickname
      archive_type = models.Post.USER_LOGIN
      logging.debug('User joined: user_id=%r, shard=%r', user_id, shard)
    else:
      logging.debug('User heartbeat: user_id=%r to shard=%r', user_id, shard)

    if archive_type:
      insert_post(
          shard,
          archive_type=archive_type,
          nickname=nickname,
          user_id=user_id,
          body=message)
    else:
      # As long as users are heart-beating, we should be running a cleanup
      # task for this shard.
      enqueue_cleanup_task(shard)

    self.json_response['userConnected'] = user_connected
    self.json_response['browserToken'] = browser_token

    # Always assign the cookie on the top domain, so the user doesn't have
    # to accept the terms of service repeatedly.
    if not config.is_dev_appserver:
      host_parts = self.request.host.split('.')
      suffix = '.'.join(host_parts[-2:])
      self.session.domain = '.' + suffix
      self.session.path = '/'

    self.session.save()


class PostHandler(BaseRpcHandler):
  """Handles users making new posts."""

  require_shard = True

  def handle(self):
    archive_type = self.get_required('type', str)
    archive_enum = models.Post.ARCHIVE_MAPPING.get(archive_type)
    if archive_enum not in models.Post.ALLOWED_ARCHIVES:
      raise BadParameterValueError(
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


class ShowRosterHandler(BaseRpcHandler):
  """Handles echoing the roster to a single user."""

  require_shard = True

  def handle(self):
    user_list = get_present_users(self.shard)
    adjusted_user_list = []
    for user in user_list:
      # Do not include ourselves in the roster.
      if user.user_id == self.user_id:
        continue
      adjusted_user_list.append(user)

    self.json_response['roster'] = marshal_users(adjusted_user_list)


class ListPostsHandler(BaseRpcHandler):
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
      # PostReference entities may point to non-existent Post entities once the
      # cleanup job has run. Filter them out here. The client side won't try to
      # scan for posts previous to the last one that's actually found, so this
      # filtering is okay.
      if not post:
        continue

      post.sequence = ref.sequence
      adjusted_post_list.append(post)

    self.json_response['posts'] = marshal_posts(self.shard, adjusted_post_list)


class CreateTopicHandler(BaseRpcHandler):
  """Create a new topic shard and returns its ID."""

  require_shard = True

  def handle(self):
    title = self.get_required(
        'title', unicode, '', html_escape=True)
    description = self.get_required(
        'description', unicode, '', html_escape=True)
    post_id = self.get_required('post_id', str)

    login_record = self.require_active_login()

    shard = models.Shard(
        id=human_uuid(),
        title=title,
        description=description,
        creation_nickname=login_record.nickname,
        root_shard=self.shard)
    shard.put()

    insert_post(
        self.shard,
        post_id=post_id,
        archive_type=models.Post.TOPIC_START,
        nickname=login_record.nickname,
        user_id=self.user_id,
        title=title,
        body=description,
        new_topic=shard.shard_id)

    self.json_response['shardId'] = shard.shard_id


class ListTopicsHandler(BaseRpcHandler):
  """Finds topics associated with a root shard and the user's read state."""

  require_shard = True

  def handle(self):
    root_shard_future = models.Shard.get_by_id_async(
        self.shard, use_cache=False, use_memcache=False)

    oldest_update_time = (
        datetime.datetime.now() -
        datetime.timedelta(seconds=config.ephemeral_lifetime_seconds))

    query = models.Shard.query()
    query = query.filter(models.Shard.root_shard == self.shard)
    query = query.filter(models.Shard.update_time > oldest_update_time)
    query = query.order(-models.Shard.update_time)
    shard_list = query.fetch(100);

    # Get the current user's readstate for each shard that was found.
    read_state_key_list = [
        ndb.Key(models.LoginRecord._get_kind(), self.user_id,
                models.ReadState._get_kind(), shard.shard_id)
        for shard in shard_list]
    read_state_list = ndb.get_multi(read_state_key_list)

    out = []
    for shard, read_state in zip(shard_list, read_state_list):
      shard_dict = dict(
        shardId=shard.shard_id,
        title=shard.title,
        description=shard.description,
        creationTimeMs=models.datetime_to_stamp_ms(shard.creation_time),
        creationNickname=shard.creation_nickname,
        updateTimeMs=models.datetime_to_stamp_ms(shard.update_time),
        sequenceNumber=shard.sequence_number,
        isRoot=shard.root_shard is None,
      )

      if read_state:
        shard_dict.update(
            firstReadTime=models.datetime_to_stamp_ms(
                read_state.first_read_time),
            lastReadSequence=read_state.last_read_sequence,
            lastReadTimeMs=models.datetime_to_stamp_ms(
                read_state.last_read_time))

      out.append(shard_dict)

    shard_record = root_shard_future.get_result()

    self.json_response['currentTopicId'] = shard_record.current_topic
    if shard_record.topic_change_time:
      self.json_response['currentTopicTimeMs'] = models.datetime_to_stamp_ms(
          shard_record.topic_change_time)
    self.json_response['topics'] = out


class ReadStateHandler(BaseRpcHandler):
  """Updates the read state for a user.

  Args:
    topic: Repeated set of shard IDs being updated.
    position: Repeated set of sequence IDs to set as read states. Each item
      in this list corresponds one-to-one with an item in the topic list.
  """

  require_shard = True

  def handle(self):
    topic_list = self.get_required('topic', str, repeated=True)
    position_list = self.get_required('position', int, repeated=True)
    if len(topic_list) != len(position_list):
      raise BadParameterValueError(
          'Must supply the same number of topics and positions')
    position_dict = dict(zip(topic_list, position_list))

    login_record = self.require_active_login()

    # TODO(bslatkin): Consider validating the topic list provided here
    # to ensure they are actually associated with the current logged-in shard.
    # The possible damage here is restricted to the user so we don't care much.
    read_state_keys = [
        ndb.Key(models.LoginRecord._get_kind(), self.user_id,
                models.ReadState._get_kind(), topic)
        for topic in topic_list]

    def txn():
      read_state_list = ndb.get_multi(read_state_keys)
      to_put = []
      for key, read_state in zip(read_state_keys, read_state_list):
        if read_state is None:
          read_state = models.ReadState(key=key)
        read_state.last_read_sequence = position_dict[key.id]
        to_put.append(read_state)

      ndb.put_multi(to_put)

    ndb.transaction(txn)

################################################################################
# UI handlers

class LandingHandler(BaseHandler):
  """Renders the landing page."""

  def get(self):
    # Treat xyz.example.com/the same as www.example.com/chat/xyz
    host_parts = self.request.host.split('.')
    if len(host_parts) > 2 and host_parts[0] != 'www':
      handler = ChatroomHandler()
      handler.initialize(self.request, self.response)
      return handler.get(host_parts[0])

    self.render('landing.html')


class TermsHandler(BaseHandler):
  """Renders the terms of service page."""

  def get(self):
    self.render('terms.html')


class CreateChatroomHandler(BaseHandler):
  """Creates a new chatroom URL and redirects the user to it."""

  def post(self):
    # TODO(bslatkin): Add XSRF protection

    shard_id = None
    while True:
      def txn():
        shard_id = human_uuid()
        shard = models.Shard.get_by_id(
            shard_id, use_cache=False, use_memcache=False)
        if shard:
          raise ndb.Rollback()
        shard = models.Shard(id=shard_id)
        shard.put()
        return shard_id

      shard_id = ndb.transaction(txn)
      if shard_id:
        break

    # For dev_appserver use the relative path. Otherwise use a sub-domain.
    if config.is_dev_appserver:
      self.redirect('/chat/' + shard_id)
    else:
      host_parts = self.request.host.split('.', 1)
      target_url = '%s://%s.%s/' % (
          self.request.scheme, shard_id, host_parts[1])
      self.redirect(target_url)


class ChatroomHandler(BaseHandler):
  """Renders a specific chatroom with the given shard ID."""

  def handle_request(self, shard_id):
    shard = models.Shard.get_by_id(shard_id)
    if not shard:
      # If the shard doesn't exist, then just create it. Makes it ridiculously
      # easy for people to create a new chat with the name of their choice.
      def txn():
        shard = models.Shard.get_by_id(
            shard_id, use_cache=False, use_memcache=False)
        if not shard:
          shard = models.Shard(id=shard_id)
          shard.put()
        return shard

      shard = ndb.transaction(txn)

    # Do not allow users to directly access topic shards.
    if shard.root_shard:
      # TODO(bslatkin): Make this pretty.
      self.response.set_status(404)
      return

    nickname = 'Anonymous'
    first_login = True
    must_accept_terms = True
    sounds_enabled = True

    if 'shards' in self.session:
      # TODO(bslatkin): Reuse presence code here.
      user_id = self.session['shards'].get(shard_id)
      if user_id:
        login_record = models.LoginRecord.get_by_id(user_id)
        if login_record and login_record.shard_id == shard_id:
          nickname = login_record.nickname
          first_login = False
          must_accept_terms = bool(
              login_record.accepted_terms_version !=
              config.terms_version)
          sounds_enabled = login_record.sounds_enabled

    context = {
      'first_login': first_login,
      'must_accept_terms': must_accept_terms,
      'nickname': xml.sax.saxutils.unescape(nickname),
      'shard_id': shard_id,
      'short_url': self.request.path_url,
      'sounds_enabled': sounds_enabled,
    }
    context['params'] = json.dumps(context)

    self.render('chatroom.html', context)


class WarmupHandler(BaseHandler):
  """Handles warm-up requests by doing nothing."""

  def get(self):
    pass

################################################################################

class DebugLoggingMiddleware(object):
  """Sets the log level to debug on each request. Used in dev_appserver."""

  def __init__(self, app):
    self.app = app

  def __call__(self, environ, start_response):
    logging.getLogger().setLevel(logging.DEBUG)
    return self.app(environ, start_response)


ROUTES = webapp.WSGIApplication([
  (r'/', LandingHandler),
  (r'/create', CreateChatroomHandler),
  (r'/terms', TermsHandler),
  (r'/_ah/warmup', WarmupHandler),
  (r'/work/apply_posts', ApplyWorker),
  (r'/work/cleanup', ShardCleanupHandler),
  (r'/rpc/show_roster', ShowRosterHandler),
  (r'/rpc/list_posts', ListPostsHandler),
  (r'/rpc/post', PostHandler),
  (r'/rpc/presence', PresenceHandler),
  (r'/rpc/create_topic', CreateTopicHandler),
  (r'/rpc/list_topics', ListTopicsHandler),
  (r'/rpc/read_state', ReadStateHandler),
  (r'/chat/([a-zA-Z0-9-]{1,100})', ChatroomHandler)
], debug=config.debug)


SESSION_OPTS = {
  'session.type': 'cookie',
  'session.key': '8bits',
  'session.httponly': True,
  'session.secure': not config.debug,
  'session.cookie_expires': False,
  'session.validate_key': config.session_validate_key,
  'session.encrypt_key': config.session_encrypt_key,
}


APP = middleware.SessionMiddleware(ROUTES, SESSION_OPTS)

if config.debug:
  APP = DebugLoggingMiddleware(APP)

if config.appstats:
  APP = recording.appstats_wsgi_middleware(APP)
