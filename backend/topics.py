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

"""Topic system."""

import datetime

# Local libs
import base
import config
import models
import ndb
import posts


@ndb.tasklet
def list_topics(root_shard_id, user_id):
  """Lists topics for a root shard and associated read state for the user.

  Args:
    root_shard_id: Shard ID of the root with associated topics.
    user_id: User ID that is requesting the list of topics and read states.

  Returns:
    Tuple (root_shard, shard_and_state_list) where:
      root_shard: Shard entity for the root.
      shard_and_state_list: List of pairs (Shard, ReadState) for associated
        topics and read states for the given user_id. Will be in order
        of update_time with most recently updated shards first.
  """
  root_shard_future = models.Shard.get_by_id_async(
      root_shard_id, use_cache=False, use_memcache=False)

  oldest_update_time = (
      datetime.datetime.now() -
      datetime.timedelta(seconds=config.ephemeral_lifetime_seconds))

  query = models.Shard.query()
  query = query.filter(models.Shard.root_shard == root_shard_id)
  query = query.filter(models.Shard.update_time > oldest_update_time)
  query = query.order(-models.Shard.update_time)
  shard_list = yield query.fetch_async(100)

  # Get the current user's readstate for each shard that was found.
  read_state_key_list = [
      ndb.Key(models.LoginRecord._get_kind(), user_id,
              models.ReadState._get_kind(), shard.shard_id)
      for shard in shard_list]
  read_state_list = yield ndb.get_multi_async(read_state_key_list)
  shard_and_state_list = zip(shard_list, read_state_list)

  root_shard = yield root_shard_future

  raise ndb.Return((root_shard, shard_and_state_list))


def update_read_state(topic_dict, user_id):
  """Updates a user's read state for a given set of topics.

  Will inherit transaction state on user_id's LoginRecord if this is
  called from within an existing transition.

  Args:
    topic_dict: Maps topioc shard IDs to the new sequence number to assign
      for that shard.
    user_id: User ID that is being updated.
  """

  # TODO(bslatkin): Consider validating the topic list provided here
  # to ensure they are actually associated with the current logged-in shard.
  # The possible damage here is restricted to the user so we don't care much.
  read_state_keys = [
      ndb.Key(models.LoginRecord._get_kind(), user_id,
              models.ReadState._get_kind(), topic)
      for topic in topic_dict]

  def txn():
    read_state_list = ndb.get_multi(read_state_keys)
    to_put = []
    for key, read_state in zip(read_state_keys, read_state_list):
      next_read_sequence = topic_dict[key.id()]
      if read_state is None:
        read_state = models.ReadState(key=key)
        read_state.last_read_sequence = next_read_sequence
      else:
        read_state.last_read_sequence = max(
            read_state.last_read_sequence, next_read_sequence)

      to_put.append(read_state)

    ndb.put_multi(to_put)

  if ndb.in_transaction():
    txn()
  else:
    ndb.transaction(txn)


class CreateTopicHandler(base.BaseRpcHandler):
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
        id=models.human_uuid(),
        title=title,
        description=description,
        creation_nickname=login_record.nickname,
        root_shard=self.shard)
    shard.put()

    posts.insert_post(
        self.shard,
        post_id=post_id,
        archive_type=models.Post.TOPIC_START,
        nickname=login_record.nickname,
        user_id=self.user_id,
        title=title,
        body=description,
        new_topic=shard.shard_id)

    self.json_response['shardId'] = shard.shard_id


class ListTopicsHandler(base.BaseRpcHandler):
  """Finds topics associated with a root shard and the user's read state."""

  require_shard = True

  def handle(self):
    shard_record, shard_and_state_list = list_topics(
        self.shard, self.user_id).get_result()

    out = []
    for shard, read_state in shard_and_state_list:
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

    self.json_response['currentTopicId'] = shard_record.current_topic
    if shard_record.topic_change_time:
      self.json_response['currentTopicTimeMs'] = models.datetime_to_stamp_ms(
          shard_record.topic_change_time)
    self.json_response['topics'] = out


class ReadStateHandler(base.BaseRpcHandler):
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
      raise base.BadParameterValueError(
          'Must supply the same number of topics and positions')
    position_dict = dict(zip(topic_list, position_list))

    self.require_active_login()

    update_read_state(position_dict, self.user_id)


ROUTES = [
  (r'/rpc/create_topic', CreateTopicHandler),
  (r'/rpc/list_topics', ListTopicsHandler),
  (r'/rpc/read_state', ReadStateHandler),
]
