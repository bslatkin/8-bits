#!/usr/bin/env python
#
# Copyright 2013 Brett Slatkin
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

"""Tests for the posts module."""

import json
import logging
import unittest

from google.appengine.ext import testbed

import config
import models
import posts
import presence


class PostTaskTest(unittest.TestCase):
    """Tests for inserting and applying Post tasks."""

    def setUp(self):
        logging.getLogger().setLevel(logging.DEBUG)
        self.maxDiff = 10**10
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_channel_stub()
        self.testbed.init_datastore_v3_stub()
        self.testbed.init_memcache_stub()
        self.testbed.init_taskqueue_stub(root_path=config.root_dir)

    def testSingle(self):
        """Tests successfully inserting and applying a single Post."""
        shard = models.Shard(id='my-shard-name')
        shard.put()

        post_key = posts.insert_post(
            shard.shard_id,
            post_id='my-id-1234',
            archive_type=models.Post.CHAT,
            nickname='My name',
            user_id='abc',
            body='Here is my message')

        found_post = models.Post.query().get()
        self.assertEquals(post_key, found_post.key)

        self.assertEquals(None, models.PostReference.query().get())
        self.assertEquals(None, models.Receipt.query().get())

        posts.apply_posts(shard.shard_id)

        found_ref = models.PostReference.query().get()
        self.assertEquals(1, found_ref.key.id())
        self.assertEquals(found_post.post_id, found_ref.post_id)

        found_receipt = models.Receipt.query().get()
        self.assertEquals(post_key, found_receipt.key.parent())

        shard_after = shard.key.get()
        self.assertEquals(2, shard_after.sequence_number)

    def testMultiple(self):
        """Tests inserting multiple posts and applying them together."""
        shard = models.Shard(id='my-shard-name')
        shard.put()

        post_key_list = []
        for i in xrange(5):
            post_key_list.append(posts.insert_post(
                shard.shard_id,
                post_id='my-id-%d' % i,
                archive_type=models.Post.CHAT,
                nickname='My name',
                user_id='abc',
                body='Here is my message %d' % i))

        self.assertEquals(5, models.Post.query().count())
        self.assertEquals(None, models.PostReference.query().get())

        posts.apply_posts(shard.shard_id)
        ref_list = list(models.PostReference.query())
        ref_ids = [r.key.id() for r in ref_list]
        self.assertEquals([1, 2, 3, 4, 5], ref_ids)

        receipt_list = list(models.Receipt.query())
        receipt_parents = [r.key.parent() for r in receipt_list]
        self.assertEquals(post_key_list, receipt_parents)

        shard_after = shard.key.get()
        self.assertEquals(6, shard_after.sequence_number)

    def testReceiptExists(self):
        """Tests that post receipts prevent duplicate PostReferences."""
        shard = models.Shard(id='my-shard-name')
        shard.put()

        already_posted_key = posts.insert_post(
            shard.shard_id,
            post_id='my-id-1234',
            archive_type=models.Post.CHAT,
            nickname='My name',
            user_id='abc',
            body='Here is my message')

        models.Receipt(id=shard.shard_id, parent=already_posted_key).put()

        new_post_key = posts.insert_post(
            shard.shard_id,
            post_id='my-id-7890',
            archive_type=models.Post.CHAT,
            nickname='My name',
            user_id='abc',
            body='My second message')

        posts.apply_posts(shard.shard_id)

        ref_list = list(models.PostReference.query())
        self.assertEquals(1, len(ref_list))
        found_ref = ref_list[0]
        self.assertEquals(new_post_key.id(), found_ref.post_id)

    def testChannelMessage(self):
        """Tests that post and apply both send message updates."""
        shard = models.Shard(id='my-shard-name')
        shard.put()

        channel_stub = self.testbed.get_stub(testbed.CHANNEL_SERVICE_NAME)
        user_id = 'my-user-id'
        presence.user_logged_in(shard.shard_id, user_id)
        _, browser_token = presence.change_presence(
            shard.shard_id, user_id, 'name here', True, True, False)
        channel_stub.connect_channel(browser_token)

        # This clears the presence Post from change_presence()
        posts.apply_posts(shard.shard_id)
        channel_stub.pop_first_message(browser_token)

        post_key = posts.insert_post(
            shard.shard_id,
            archive_type=models.Post.CHAT,
            nickname='My name',
            user_id='abc',
            body='Here is my message')

        message = channel_stub.pop_first_message(browser_token)
        found_posts = json.loads(message)['posts']
        post = post_key.get()
        expected_posts = posts.marshal_posts(shard.shard_id, [post])
        self.assertEquals(expected_posts, found_posts)
        self.assertEquals(None, expected_posts[0]['sequenceId'])

        posts.apply_posts(shard.shard_id)
        post = post_key.get()
        message = channel_stub.pop_first_message(browser_token)
        found_posts = json.loads(message)['posts']
        self.assertEquals(2, found_posts[0]['sequenceId'])
        post = post_key.get()
        post.sequence = 2  # Pretend to do what apply_posts does
        expected_posts = posts.marshal_posts(shard.shard_id, [post])
        self.assertEquals(expected_posts, found_posts)


if __name__ == '__main__':
    unittest.main()
