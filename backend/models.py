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

- LoginRecord: Record of a user who's logged in. Periodically cleaned up
    if the user has not been active for some number of hours.

- Shard: Root entity for a single chat room.

  - PostReference (child): Reference to a Post entity that's periodically
      written under the Shard whenever fan-in occurs.


How do topics work?
Post: Used as a reference point for the topic with the topic_start event.
PostReference: Used to look up topic start events in sequence

post the posts to the normal shard, but then replicate the post references
over to an alternate shard that is the topic. then when querying for posts
you just query for them on an alternate root shard

"""

import datetime
import time

# Local imports
import config
import ndb

################################################################################
# Utilities

def datetime_to_stamp_seconds(when):
  """Converts a datetime.datetime to a timestamp in seconds since the epoch."""
  stamp = float(time.mktime(when.utctimetuple()))
  stamp += when.microsecond / 1000000.0
  return stamp

################################################################################

class Shard(ndb.Model):
  """Core reference to a single community.

  TODO explain root shards versus topic shards
  """

  @classmethod
  def _get_kind(cls):
    return 'S'

  # Immutable properties set upon shard creation.
  pretty_name = ndb.TextProperty(default='')
  description = ndb.TextProperty(default='')
  creation_time = ndb.DateTimeProperty(auto_now_add=True)
  created_nickname = ndb.TextProperty(default='')

  # Properties updated as users interact with the shard.
  update_time = ndb.DateTimeProperty(auto_now=True)
  sequence_number = ndb.IntegerProperty(default=1, indexed=False)

  # Current topic being discussed. This is the shard ID of that topic. Will
  # be unset when there is no current topic.
  current_topic = ndb.StringProperty(indexed=False)

  # Shard that owns this topic shard. Will be unset for root shards.
  # TODO(bslatkin): Don't allow users to login to shards that have a root.
  root_shard = ndb.StringProperty()

  @property
  def shard_id(self):
    return self.key.id()


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

  # Zero means no terms accepted.
  accepted_terms_version = ndb.IntegerProperty(default=0, indexed=False)


class ReadState(ndb.Model):
  """User's read state for a specific topic.

  Parent is the LoginRecord. ID is the Shard for which this is the read
  state. Must be the same as LoginRecord.shard_id unless the Shard is a topic
  shard.
  """

  @classmethod
  def _get_kind(cls):
    return 'RS'

  @property
  def shard_id(self):
    return self.key.id

  first_read_time = ndb.DateTimeProperty(auto_now_add=True, indexed=False)
  last_read_sequence = ndb.IntegerProperty(indexed=False)
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
  ALLOWED_ARCHIVES = frozenset([CHAT])

  archive_type = ndb.IntegerProperty(
      required=True, indexed=False, choices=ARCHIVE_TYPES)
  nickname = ndb.TextProperty(required=True)
  user_id = ndb.TextProperty(required=True)
  body = ndb.TextProperty(required=True)  # chat, topic intro
  post_time = ndb.DateTimeProperty(indexed=False)

  @property
  def post_id(self):
    return self.key.id()


class Receipt(ndb.Model):
  """TODO

  parent is the Post
  ID is the shard to which the post was written
  used to make sure we don't duplicate writes
  """

  @classmethod
  def _get_kind(cls):
    return 'R'

  @property
  def post_id(self):
    return self.key.parent().id()

  sequence = ndb.IntegerProperty(indexed=False)


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
