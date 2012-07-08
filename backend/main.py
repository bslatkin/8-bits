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

class PostError(Error):
  """A posting could not be made."""

################################################################################
# Utility classes, functions.

class BaseUiHandler(webapp.RequestHandler):
  """Base handler for rendering UI."""

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

  def get_required(self, name, type_constructor,
                   default=None,
                   html_escape=False):
    """Retrieves a required parameter with the given name and default."""
    value = self.request.get(name)
    if value == '':
      value = default
    if value is None:
      raise MissingParameterError('Parameter "%s" is required' % name)

    try:
      value = type_constructor(value)
    except ValueError:
      raise BadParameterValueError('Parameter "%s" has an invalid value: %r'
                                   % (name, value))

    if html_escape:
      return cgi.escape(value)
    else:
      return value

  def render(self, template_name, context=None):
    """Renders the given template and context."""
    js_mode = 'compiled'
    if (config.debug and
        self.request.environ.get('SERVER_SOFTWARE').startswith('Dev')):
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


class BaseRpcHandler(BaseUiHandler):
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
  raw_response = False  # TODO(bslatkin): Refactor this to use BaseUiHandler

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
    if shard not in self.session['shards']:
      raise NotAuthorizedError('You may not access shard %s' % shard)
    return shard


def human_uuid():
  """Generates a more human friendly UUID."""
  return base64.b32encode(uuid.uuid4().bytes).strip('=').lower()


def normalize_human_uuid(user_supplied):
  """Normalizes a UUID typed by a human.

  Replaces any '1's with 'L's, etc; following the base32 encoding style.
  """
  # TODO(bslatkin): Actually do something here
  return user_supplied


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

  post_id, if supplied, indicates to the apply task which posts it should
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
      name='apply-%s-join-%s' % (shard, join_index)
    ).add(config.apply_queue)
  except (taskqueue.TombstonedTaskError, taskqueue.TaskAlreadyExistsError):
    logging.debug('Enqueued apply task for shard=%r but task already present',
                  shard)


def insert_post(shard, **kwargs):
  """Inserts a post at the present time, returning its key.

  If the post_id keyword argument is not supplied, a new post ID will be
  auto assigned.
  """
  # Create the posting and insert it.
  post_id = kwargs.pop('post_id', None)
  if not post_id:
    post_id = human_uuid()
  post_key = ndb.Key(models.Post._get_kind(), post_id)

  if 'post_time' not in kwargs:
    kwargs['post_time'] = datetime.datetime.now()

  def txn():
    post = post_key.get(use_memcache=False, use_cache=False)
    if post:
      logging.warning('Post already exists for shard=%r, post_id=%r',
                      shard, post_id)
      raise ndb.Rollback()

    post = models.Post(
      key=post_key,
      shard_id=shard,
      **kwargs)
    post.put(use_memcache=False, use_cache=False)

    # Pull task that indicates the post to apply
    taskqueue.Task(
      method='PULL',
      tag=str(shard),
      params=dict(shard=shard, post_key=post_key.urlsafe()),
    ).add(config.pending_queue, transactional=True)

    return post

  try:
    post = ndb.transaction(txn)
  except Exception, e:
    logging.warning('Could not insert post with kwargs=%r',
                     kwargs, exc_info=True)
    raise PostError(str(e))

  # Notify all users of the post.
  futures = []
  futures.append(notify_posts(shard, [post]))

  # Set the dirty bit for this shard. This causes apply_posts to run a
  # second time if the Post transaction above completed while apply_posts
  # was already in flight.
  dirty_bit(shard, set=True)

  # Enqueue an apply task to sequence and notify the new post.
  futures.append(enqueue_apply_task(shard, post_id=post_key.id()))

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
    shard = int(params['shard'])
    logging.debug('apply_posts with no specific shard found shard=%r', shard)

  # Clear the dirty bit on this shard to start the time horizon.
  dirty_bit(shard, clear=True)

  # Find tasks pending for the current shard.
  task_list.extend(
      queue.lease_tasks_by_tag(lease_seconds, max_tasks, tag=str(shard)))

  work_key_list = []
  for task in task_list:
    params = task.extract_params()
    work_key_list.append(ndb.Key(urlsafe=params['post_key']))
  work = ndb.get_multi(work_key_list)

  # Some tasks may be in the pull queue that were already put in sequence.
  # So ignore these and only apply the new ones.
  sequence_numbers = [w.sequence for w in work if w.sequence is not None]
  unapplied_work = [w for w in work if w.sequence is None]
  new_sequence_numbers = []

  if unapplied_work:
    def txn():
      shard_record = models.Shard.get_by_id(shard)
      if shard == 1 and not shard_record:
        # Auto-create the landing page shard if it doesn't exist.
        shard_record = models.Shard(
            key=ndb.Key(models.Shard._get_kind(), shard),
            pretty_name='Landing chat')

      # Clear any new sequence numbers that were allocated but were not
      # applied due to a transaction rollback.
      new_sequence_numbers[:] = []
      new_sequence_numbers.extend(
          xrange(shard_record.sequence_number,
                 shard_record.sequence_number + len(unapplied_work)))
      shard_record.sequence_number += max(1, len(unapplied_work))

      # Write post references that point at the newly sequenced posts.
      to_put = [shard_record]
      for post, sequence in zip(unapplied_work, new_sequence_numbers):
        to_put.append(models.PostReference(
            id=sequence,
            parent=shard_record.key,
            post_id=post.post_id))
      ndb.put_multi(to_put)

    # Have this only attempt a transaction a single time. If the transaction
    # fails the task queue will retry this task within 4 seconds. Because
    # apply tasks are always named by the current Shard.sequence_number we
    # can be reasonably sure that no other apply task for this shard will be
    # running concurrently when this fails.
    ndb.transaction(txn, retries=1)

    sequence_numbers.extend(new_sequence_numbers)
    for post, sequence in zip(unapplied_work, new_sequence_numbers):
      post.sequence = sequence
    ndb.put_multi(unapplied_work)
    logging.debug('Applied %d posts for shard=%r, sequence_numbers=%r',
                  len(unapplied_work), shard, sequence_numbers)
  else:
    if not insertion_post_id:
      logging.debug('No post application to do for shard=%r')
    else:
      post = models.Post.get_by_id(insertion_post_id)
      if post and post.sequence:
        logging.warning('No post application to do for shard=%r, but'
                        'post_id=%r already applied; dropping this task',
                        shard, insertion_post_id)
      else:
        raise Error('No post application to do for shard=%r, but'
                    'post_id=%r has not been applied; will retry' %
                    (shard, insertion_post_id))

  # Notify all logged in users of the new posts.
  futures = []
  futures.append(notify_posts(shard, work))

  # Success! Delete the tasks from this queue.
  queue.delete_tasks(task_list)

  # Always run one more apply task to clean up any posts that came in
  # while this transaction was processing.
  if dirty_bit(shard, check=True):
    futures.append(enqueue_apply_task(shard))

  # Wait on all pending futures in case they raise errors.
  ndb.Future.wait_all(futures)


def marshal_posts(post_list):
  """Organizes a list of posts into a JSON-serializable list."""
  out = []
  for post in post_list:
    post_dict = dict(
      shardId=post.shard_id,
      archiveType=models.Post.ARCHIVE_REVERSE_MAPPING[post.archive_type],
      nickname=post.nickname,
      body=post.body,
      postTimeMs=int(
          models.datetime_to_stamp_seconds(post.post_time) * 1000),
      sequenceId=post.sequence,
      postId=post.post_id)
    if post.post_name:
      post_dict.update(dict(postName=post.post_name))
    if post.post_attachment:
      post_dict.update(dict(
          postAttachment='/file/download?shard=%d&post_id=%s' %
                          (post.shard_id, post.post_id)))
    out.append(post_dict)
  return out


def _GetChannelServiceName():
  """Gets the service name to use, based on if we're on the dev server."""
  if os.environ.get('SERVER_SOFTWARE', '').startswith('Devel'):
    return 'channel'
  else:
    return 'xmpp'


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
def notify_posts(shard, post_list):
  """Notifies logged-in users of a set of new posts."""
  if not post_list:
    return

  posts_json = json.dumps({
    'posts': marshal_posts(post_list),
  })

  login_record_list = get_present_users(shard)
  rpc_list = []
  for login_record in login_record_list:
    logging.debug('Informing shard=%r, user=%r, nickname=%r about messages '
                  'with sequence_numbers=%r', shard, login_record.user_id,
                  login_record.nickname, [p.sequence for p in post_list])
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


def get_present_users(shard):
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

  # TODO(bslatkin): Better serialization, paging for > 1000 users.
  user_list = (models.LoginRecord.query()
      .filter(models.LoginRecord.shard_id == shard)
      .filter(models.LoginRecord.online == True)
      .order(-models.LoginRecord.last_update_time)
      .fetch(1000))
  memcache.set(shard_key, user_list, 300)
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
    login_record.online = False
    login_record.put()
    return login_record
  login_record = ndb.transaction(txn)

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

class ApplyWorker(webapp.RequestHandler):
  """Applies pending posts."""

  def post(self):
    shard = self.request.get('shard')
    post_id = self.request.get('post_id')
    apply_posts(shard=shard, insertion_post_id=post_id)

  def get(self):
    apply_posts()

################################################################################
# RPC handlers

class CreateShardHandler(BaseRpcHandler):
  """Creates new shards."""

  def handle(self):
    pretty_name = self.get_required('pretty', str)
    shard = models.Shard(pretty_name=pretty_name)
    shard.put()
    self.json_response['shardId'] = shard.shard_id


class LoginHandler(BaseRpcHandler):
  """Handles user logins, logouts, and issuing session cookies."""

  def handle(self):
    shard = self.get_required('shard', str)
    mode = self.get_required('mode', str)

    if 'shards' not in self.session:
      # First login with no cookie present.
      self.session['shards'] = {}

    if mode.lower() == 'join':
      user_id = self.session['shards'].get(shard)
      user_id = user_logged_in(shard, user_id)

      # Always issue a new browser channel ID for the user if their
      # session is in good shape.
      self.session['shards'][shard] =  user_id
      browser_token = channel.create_channel(get_token(user_id))
      self.json_response['browserToken'] = browser_token
    elif mode.lower() == 'leave' and shard in self.session['shards']:
      user_id = self.session['shards'][shard]
      user_logged_out(shard, user_id)

    self.session.save()


class PresenceHandler(BaseRpcHandler):
  """Handles updating user presence."""

  require_shard = True

  def handle(self):
    nickname = self.get_required('nickname', str, html_escape=True)
    accepted_terms = self.get_required('accepted_terms', str, '') == 'true'

    last_nickname = [None]
    def txn():
      # TODO(bslatkin): Verify the login is active and valid (max age).
      login = models.LoginRecord.get_by_id(self.user_id)
      last_nickname[0] = login.nickname
      login.nickname = nickname
      if accepted_terms:
        login.accepted_terms_version = config.terms_version
      login.put()
    ndb.transaction(txn)

    # Invalidate the cache so the nickname will be updated next time
    # someone requests the roster.
    invalidate_user_cache(self.shard)

    message = '%s has joined' % nickname
    archive_type = models.Post.USER_LOGIN
    if last_nickname[0] != nickname:
      message = '%s has changed their nickname to %s' % (
          last_nickname[0], nickname)
      archive_type = models.Post.USER_UPDATE

    insert_post(
        self.shard,
        archive_type=archive_type,
        nickname=nickname,
        user_id=self.user_id,
        body=message)

    logging.debug('Presence updated for user_id=%r in shard=%r',
                  self.user_id, self.shard)


class ChannelPresenceHandler(webapp.RequestHandler):
  """Handles user disconnect presence notifications."""

  def post(self, action):
    if action.startswith('disconnected'):
      client_id = self.request.get('from')
      logging.info('disconnected! %s', client_id)
      login_record = models.LoginRecord.get_by_id(client_id)
      if not login_record:
        logging.warning('Channel client_id=%r has no associated LoginRecord',
                        client_id)
        return

      user_logged_out(login_record.shard_id, client_id)


class PostHandler(BaseRpcHandler):
  """Handles users making new posts."""

  require_shard = True

  def handle(self):
    archive_type = self.get_required('type', str)
    archive_enum = models.Post.ARCHIVE_MAPPING.get(archive_type)
    if archive_enum not in models.Post.ALLOWED_ARCHIVES:
      raise BadParameterValueError(
          '"%s" is not a valid post type' % archive_type)
    body = self.get_required('body', str, html_escape=True)
    post_id = self.get_required('post_id', str)

    # TODO(bslatkin): Verify the login is active and valid (max age).
    login_record = models.LoginRecord.get_by_id(self.user_id)
    post_key = insert_post(
      self.shard,
      post_id=post_id,
      archive_type=archive_enum,
      nickname=login_record.nickname,
      user_id=login_record.user_id,
      body=body)
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

    self.json_response['posts'] = marshal_posts(post_list)

################################################################################
# File-related handlers

# TODO(bslatkin): Reenable these.
#
# class StartUploadHandler(BaseRpcHandler):
#   """Handles getting new upload URLs for files."""
# 
#   get_enabled = True
#   post_enabled = False
#   require_shard = True
# 
#   def handle(self):
#     # TODO(bslatkin): Verify the login is active and valid (max age).
#     return blobstore.create_upload_url('/work/upload_end')
# 
# 
# class EndUploadHandler(BaseRpcHandler,
#                        blobstore_handlers.BlobstoreUploadHandler):
#   """Handles completing a file upload."""
# 
#   require_shard = True
#   raw_response = True
# 
#   def handle(self):
#     upload_files = self.get_uploads('file')
#     blob_info = upload_files[0]
#     filename = cgi.escape(blob_info.filename)
# 
#     # TODO(bslatkin): Verify the login is active and valid (max age).
#     login_record = models.LoginRecord.get_by_id(self.user_id)
#     post_key = insert_post(
#       self.shard,
#       archive_type=models.Post.FILE,
#       nickname=login_record.nickname,
#       user_id=login_record.user_id,
#       body='The file "%s" has been uploaded' % filename,
#       post_name=filename,
#       post_attachment=blob_info.key())
# 
#     self.redirect('/file/upload_complete?shard=%d&post_id=%s' %
#                   (self.shard, post_key.id()))
# 
# 
# class CompleteUploadHandler(BaseRpcHandler):
#   """Echos the post ID of a completed file upload."""
# 
#   get_enabled = True
#   post_enabled = False
#   require_shard = True
# 
#   def handle(self):
#     self.json_response['postId'] = self.get_required('post_id', str)
# 
# 
# class DownloadFileHandler(BaseRpcHandler):
#   """Gives users access to a file for download."""
# 
#   get_enabled = True
#   post_enabled = False
#   require_shard = True
#   raw_response = True
# 
#   def handle(self):
#     post_id = self.get_required('post_id', str)
#     post = models.Post.get_by_id(post_id)
# 
#     if not post:
#       raise NotAuthorizedError('Non-existent post')
#     if post.shard_id != self.shard:
#       raise NotAuthorizedError('Invalid shard ID')
#     if post.archive_type != models.Post.FILE:
#       raise NotAuthorizedError('Post type is not a file')
# 
#     self.response.headers[blobstore.BLOB_KEY_HEADER] = str(
#         post.post_attachment.key())
#     # Use blob's default content-type.
#     del self.response.headers['Content-Type']

################################################################################
# UI handlers

class LandingHandler(BaseUiHandler):
  """Renders the landing page."""

  def get(self):
    self.render('landing.html')


class TermsHandler(BaseUiHandler):
  """Renders the terms of service page."""

  def get(self):
    self.render('terms.html')


class CreateChatroomHandler(BaseUiHandler):
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

    self.redirect('/chat/' + shard_id)


class ChatroomHandler(BaseUiHandler):
  """Renders a specific chatroom with the given shard ID."""

  def handle_request(self, shard_id):
    normalized = normalize_human_uuid(shard_id)
    if normalized != shard_id:
      self.redirect('/' + normalized)
      return

    shard = models.Shard.get_by_id(shard_id)
    if not shard:
      # TODO(bslatkin): Pretty 404
      self.response.set_status(404)
      self.response.out.write('Unknown shard')
      return

    nickname = 'Anonymous'
    first_login = True
    must_accept_terms = True
    if 'shards' in self.session:
      user_id = self.session['shards'].get(shard_id)
      if user_id:
        login_record = models.LoginRecord.get_by_id(user_id)
        if login_record.shard_id == shard_id:
          nickname = login_record.nickname
          first_login = False
          must_accept_terms = bool(
              login_record.accepted_terms_version !=
              config.terms_version)

    context = {
      'first_login': first_login,
      'must_accept_terms': must_accept_terms,
      'nickname': nickname,
      'shard_id': shard_id,
      'short_url_prefix': self.request.host_url,
    }
    context['params'] = json.dumps(context)

    self.render('chatroom.html', context)


class DebugFormHandler(BaseUiHandler):
  """Serves the debug form for admins."""

  def get(self):
    context = {
      'upload_file_path': blobstore.create_upload_url('/work/upload_end'),
    }
    self.render('debug_forms.html', context)


class WarmupHandler(BaseUiHandler):
  """Handles warm-up requests by doing nothing."""

  def get(self):
    pass

################################################################################


ROUTES = webapp.WSGIApplication([
  (r'/', LandingHandler),
  (r'/create', CreateChatroomHandler),
  (r'/terms', TermsHandler),
  (r'/_ah/warmup', WarmupHandler),
  (r'/_ah/channel/([^/]+)/', ChannelPresenceHandler),
  (r'/admin/debug', DebugFormHandler),
  (r'/work/apply_posts', ApplyWorker),
  (r'/rpc/create_shard', CreateShardHandler),
  (r'/rpc/show_roster', ShowRosterHandler),
  (r'/rpc/list_posts', ListPostsHandler),
  (r'/rpc/login', LoginHandler),
  (r'/rpc/post', PostHandler),
  (r'/rpc/presence', PresenceHandler),
  # TODO(bslatkin): Reenable these
  # (r'/work/upload_end', EndUploadHandler),
  # (r'/file/upload_start', StartUploadHandler),
  # (r'/file/upload_complete', CompleteUploadHandler),
  # (r'/file/download', DownloadFileHandler),
  (r'/chat/([a-z0-9A-Z]+)', ChatroomHandler)
], debug=config.debug)


SESSION_OPTS = {
  'session.type': 'cookie',
  'session.key': '8bits',
  'session.validate_key': config.session_validate_key,
  'session.encrypt_key': config.session_encrypt_key,
}


APP = middleware.SessionMiddleware(ROUTES, SESSION_OPTS)

## Enable appstats
# APP = recording.appstats_wsgi_middleware(APP)
