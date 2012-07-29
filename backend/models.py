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
  - PostReference: Reference to a Post entity that's periodically written
      under the Shard whenever fan-in occurs.
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
  """Core reference to a single community."""

  @classmethod
  def _get_kind(cls):
    return 'S'

  pretty_name = ndb.StringProperty(default='')
  creation_time = ndb.DateTimeProperty(auto_now_add=True)
  update_time = ndb.DateTimeProperty(auto_now=True)
  sequence_number = ndb.IntegerProperty(indexed=False, default=1)

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
  # Zero means no terms accepted.
  accepted_terms_version = ndb.IntegerProperty(default=0, indexed=False)


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
  NEWS = 30
  FILE = 40

  ARCHIVE_TYPES = frozenset([
    USER_LOGIN,
    USER_LOGOUT,
    USER_UPDATE,
    CHAT,
    NEWS,
    FILE,
  ])
  ARCHIVE_MAPPING = {
    'chat': CHAT,
    'news': NEWS,
    'file': FILE,
    'user_login': USER_LOGIN,
    'user_logout': USER_LOGOUT,
    'user_update': USER_UPDATE,
  }
  ARCHIVE_REVERSE_MAPPING = dict((v, k) for k, v in ARCHIVE_MAPPING.items())

  # Allowed post types directly from users.
  ALLOWED_ARCHIVES = frozenset([CHAT, NEWS, FILE])

  archive_type = ndb.IntegerProperty(required=True, choices=ARCHIVE_TYPES)
  nickname = ndb.TextProperty(required=True)
  user_id = ndb.TextProperty(required=True)
  body = ndb.TextProperty(required=True)  # chat, news post, file description
  post_name = ndb.TextProperty()  # eg, filename, news post title
  post_attachment = ndb.BlobKeyProperty(indexed=False)  # the file
  post_time = ndb.DateTimeProperty(indexed=False)

  # Which Shard this happened on and in what order.
  shard_id = ndb.StringProperty(required=True, indexed=False)
  sequence = ndb.IntegerProperty(indexed=False)

  @property
  def post_id(self):
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
