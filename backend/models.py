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

"""Models for the 8-bits chat system.

- Post: Root entity for a single user post. Inserts quickly into a separate
      entity group. Put in order in a Shard by PostReference entities.

  - Receipt (child): Indicates that a shard has written this post and put it
      in order. Allows one Post to existing in multiple shards at a time.

- LoginRecord: Record of a user who's logged in. Periodically cleaned up
    if the user has not been active for some number of hours. May be a pseudo
    entity that's only present in the key of children (e.g., for maintaining
    the read state of an email address to notify).

  - ReadState (child): Saves the state of what the user has read on a given
      shard. Lets the UI scroll the history to that starting position when the
      user relogins in to a shard (or views a specific topic shard).

- Shard: Root entity for a single chat room.

  - PostReference (child): Reference to a Post entity that's periodically
      written under the Shard whenever fan-in occurs.
"""

import base64
import datetime
import hashlib
import time
import uuid

# Local imports
import config
import ndb

###############################################################################
# Utilities

def datetime_to_stamp_seconds(when):
  """Converts a datetime.datetime to a timestamp in seconds since the epoch."""
  stamp = float(time.mktime(when.utctimetuple()))
  stamp += when.microsecond / 1000000.0
  return stamp


def datetime_to_stamp_ms(when):
  """Converts a datetime to a timestamp in milliseconds since the epoch."""
  return int(datetime_to_stamp_seconds(when) * 1000.0)


def human_bytes(byte_string):
  """Generates more human friendly representation of a byte string."""
  return base64.b32encode(byte_string).strip('=').lower()


def human_uuid():
  """Generates a more human friendly UUID."""
  return human_bytes(uuid.uuid4().bytes)


def human_hash(data):
  """Generates a more human friendly hash of data."""
  return human_bytes(hashlib.sha1(data).digest())


###############################################################################

class Shard(ndb.Model):
  """Core reference to a single chatroom or a topic within that chatroom."""

  @classmethod
  def _get_kind(cls):
    return 'S'

  # Immutable properties set upon shard creation. For topic shards, title
  # will probably contain a URL. The description of the topic is what the
  # initial user supplied at topic creation time.
  title = ndb.TextProperty(default='')
  description = ndb.TextProperty(default='')
  creation_nickname = ndb.TextProperty(default='')
  creation_time = ndb.DateTimeProperty(auto_now_add=True)

  # Properties updated as users interact with the shard.
  update_time = ndb.DateTimeProperty(auto_now=True)
  sequence_number = ndb.IntegerProperty(default=1, indexed=False)

  # Shard ID of the current topic being discussed. Unset when there is no
  # current topic. Only set for root shards.
  current_topic = ndb.StringProperty(indexed=False)
  topic_change_time = ndb.DateTimeProperty(indexed=False)

  # Shard ID that owns this topic shard. Will be unset for root shards.
  root_shard = ndb.StringProperty()

  @property
  def shard_id(self):
    return self.key.id()


class PostReference(ndb.Model):
  """Reference to a Post that exists under a Shard entity.

  Ensures that transactional queries on a Shard will find all associated posts
  when using the high-replication datastore.

  Parent is the Shard. Key name is the sequence number for the post.
  """

  @classmethod
  def _get_kind(cls):
    return 'PR'

  @property
  def shard_id(self):
    return self.key.parent().id()

  @property
  def sequence(self):
    return self.key.id()

  # The key name of the Post that has this sequence number. Usually a UUID.
  post_id = ndb.TextProperty()


class LoginRecord(ndb.Model):
  """Record of a user who is logged in.

  Key name is an auto-assigned ID.
  """

  @classmethod
  def _get_kind(cls):
    return 'LR'

  @property
  def user_id(self):
    return self.key.id()

  shard_id = ndb.StringProperty(required=True)
  online = ndb.BooleanProperty(required=True)
  creation_time = ndb.DateTimeProperty(auto_now_add=True, indexed=False)
  last_update_time = ndb.DateTimeProperty(auto_now=True)
  nickname = ndb.TextProperty()
  browser_token = ndb.TextProperty()
  browser_token_issue_time = ndb.DateTimeProperty(indexed=False)
  sounds_enabled = ndb.BooleanProperty(default=True, indexed=False)
  email_address = ndb.StringProperty()

  # Zero means no terms accepted.
  accepted_terms_version = ndb.IntegerProperty(default=0, indexed=False)


class EmailRecord(ndb.Model):
  """Record of an email address used for notifications.

  Key name is the destination email address.
  """

  @classmethod
  def _get_kind(cls):
    return 'ER'

  @property
  def email_address(self):
    return self.key.id()

  sequence_number = ndb.IntegerProperty(default=1, indexed=False)
  creation_time = ndb.DateTimeProperty(auto_now_add=True)
  last_update_time = ndb.DateTimeProperty(auto_now=True)
  last_notified_time = ndb.DateTimeProperty()
  secret = ndb.TextProperty()

  global_opt_out = ndb.BooleanProperty(default=False)
  min_notify_period_seconds = ndb.IntegerProperty(indexed=False, default=900)


class ReadState(ndb.Model):
  """User's read state for a specific shard (applies to root and topic shards).

  Parent is the LoginRecord. ID is the Shard for which this is the read state.
  """

  @classmethod
  def _get_kind(cls):
    return 'RS'

  @property
  def shard_id(self):
    return self.key.id()

  first_read_time = ndb.DateTimeProperty(auto_now_add=True, indexed=False)
  last_read_sequence = ndb.IntegerProperty(default=1, indexed=False)
  last_read_time = ndb.DateTimeProperty(auto_now=True, indexed=False)


class Post(ndb.Model):
  """Archived post.

  Key name is a randomly assigned UUID. All posts are root entities.
  """

  @classmethod
  def _get_kind(cls):
    return 'P'

  # Types of posts.
  USER_LOGIN = 10
  USER_LOGOUT = 11
  USER_UPDATE = 12
  CHAT = 20
  TOPIC_START = 50
  TOPIC_CHANGE = 51

  ARCHIVE_TYPES = frozenset([
    USER_LOGIN,
    USER_LOGOUT,
    USER_UPDATE,
    CHAT,
    TOPIC_START,
    TOPIC_CHANGE,
  ])
  ARCHIVE_MAPPING = {
    'chat': CHAT,
    'user_login': USER_LOGIN,
    'user_logout': USER_LOGOUT,
    'user_update': USER_UPDATE,
    'topic_start': TOPIC_START,
    'topic_change': TOPIC_CHANGE,
  }
  ARCHIVE_REVERSE_MAPPING = dict((v, k) for k, v in ARCHIVE_MAPPING.items())

  # Allowed post types directly from users.
  ALLOWED_ARCHIVES = frozenset([CHAT, TOPIC_CHANGE])

  archive_type = ndb.IntegerProperty(
      required=True, indexed=False, choices=ARCHIVE_TYPES)
  nickname = ndb.TextProperty(required=True)
  user_id = ndb.TextProperty(required=True)
  post_time = ndb.DateTimeProperty(indexed=False)
  title = ndb.TextProperty()
  body = ndb.TextProperty(required=True)
  new_topic = ndb.TextProperty()

  @property
  def post_id(self):
    return self.key.id()


class Receipt(ndb.Model):
  """Indicates that a post has been written to a shard in sequence.

  Parent is the Post entity that was written. ID is the shard to which the
  post was written. Used to make sure we don't duplicate writes.
  """

  @classmethod
  def _get_kind(cls):
    return 'R'

  @property
  def post_id(self):
    return self.key.parent().id()

  sequence = ndb.IntegerProperty(indexed=False)
