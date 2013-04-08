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

"""User login and presence."""

import datetime
import logging
import time

from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.api.channel import channel

# Local libs
import base
import config
import models
import ndb
import posts
import send_email


def invalidate_user_cache(shard):
  """Invalidates the present user cache for the given shard."""
  # Memcache keys from get_present_users()
  memcache.delete_multi([
      'users-shard-%s' % shard,
      'users-shard-%s-stale' % shard])


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


def get_present_users(shard, include_stale=False, limit=1000):
  """Returns a list of present users for a shard in descending log-in order.

  Notably, this query is going to be eventually consistent and miss the folks
  who have just recently joined. That's okay. It's like they joined the chat
  a little bit late. They will still be able to see previous Posts through
  historical queries.
  """
  shard_key = 'users-shard-%s' % shard
  if include_stale:
    shard_key = '%s-stale' % shard_key

  user_list = memcache.get(shard_key)
  if user_list:
    return user_list

  query = models.LoginRecord.query()
  query = query.filter(models.LoginRecord.shard_id == shard)

  # When we don't care about stale users, select everyone in the query,
  # including users we know are already logged out.
  if not include_stale:
    query = query.filter(models.LoginRecord.online == True)

  query.order(-models.LoginRecord.last_update_time)
  user_list = query.fetch(limit)

  if not include_stale:
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
      key=ndb.Key(models.LoginRecord._get_kind(), models.human_uuid()),
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

  posts.insert_post(
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


def enqueue_cleanup_task(shard):
  """Enqueues a task to invoke the ShardCleanupWorker periodically."""
  # In case the ShardCleanupWorker runs early, make sure that the task name
  # it generates for continuation is guaranteed to run.
  offset = time.time() / config.shard_cleanup_period_seconds
  name = 'cleanup-%s-time-%d' % (shard, offset)
  if name == config.request.environ.get('HTTP_X_APPENGINE_TASKNAME'):
    offset += 1
    name = 'cleanup-%s-time-%d' % (shard, offset)

  try:
    taskqueue.Task(
      url='/work/cleanup',
      params=dict(shard=shard),
      name='cleanup-%s-time-%d' % (
          shard, time.time() / config.shard_cleanup_period_seconds),
      countdown=config.shard_cleanup_period_seconds
    ).add(config.cleanup_queue)
  except (taskqueue.TombstonedTaskError, taskqueue.TaskAlreadyExistsError):
    logging.debug('Enqueued cleanup task for shard=%r but task '
                  'already present', shard)


class ShardCleanupWorker(base.BaseHandler):
  """Handles periodic cleanup requests for a specific shard.

  This handler will run periodically (~minute) for all shards that have
  active participants. It's meant to do state cleanup for the shard, such as
  forcing logouts for users who have not heartbeated in N seconds.

  This handler will also enqueue any other periodic tasks that need to
  happen for the shard.
  """

  def post(self):
    shard = self.get_required('shard', str)

    all_users_list = get_present_users(shard, include_stale=True, limit=10000)

    # Find users who are now stale and log them out.
    active_users_list = only_active_users(*all_users_list)
    all_users_set = set(u.user_id for u in all_users_list)
    active_users_set = set(u.user_id for u in active_users_list)

    for user_id in (all_users_set - active_users_set):
      user_logged_out(shard, user_id)

    # Enqueue email notification tasks for users
    emails_set = set(u.email_address
                     for u in all_users_list if u.email_address)
    send_email.enqueue_email_tasks(emails_set)

    # As long as there are still active users, continue to try to
    # clean them up.
    if active_users_set:
      enqueue_cleanup_task(shard)


class PresenceHandler(base.BaseRpcHandler):
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
      raise base.TopicShardError('Cannot login to topic shard')

    if 'shards' not in self.session:
      # First login on any shard with no cookie present.
      self.session['shards'] = {}

    user_id = self.session['shards'].get(shard)
    if not user_id:
      # First login to this shard.
      user_id = models.human_uuid()
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
      posts.insert_post(
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


class ShowRosterHandler(base.BaseRpcHandler):
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


ROUTES = [
  (r'/rpc/show_roster', ShowRosterHandler),
  (r'/rpc/presence', PresenceHandler),
  (r'/work/cleanup', ShardCleanupWorker),
]
