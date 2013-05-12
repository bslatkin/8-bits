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

"""Tests for the send_email module."""

import json
import logging
import os
import unittest

from google.appengine.ext import testbed

import config
import models
import posts
import presence
import send_email
import topics


class SendEmailTest(unittest.TestCase):
    """Tests for sending email digests."""

    def setUp(self):
        logging.getLogger().setLevel(logging.DEBUG)
        self.maxDiff = 10**10
        root_path = os.getcwd()
        self.testbed = testbed.Testbed()
        self.testbed.activate()
        self.testbed.init_channel_stub()
        self.testbed.init_datastore_v3_stub(
            root_path=root_path,
            use_sqlite=True,
            require_indexes=True)
        self.testbed.init_mail_stub()
        self.testbed.init_memcache_stub()
        self.testbed.init_taskqueue_stub(root_path=root_path)

        self.shard = models.Shard(id='my-shard-name')
        self.shard.put()
        self.user_id = 'abc'

    def tearDown(self):
        self.testbed.deactivate()

    def testNoTopics(self):
        """Tests sending the digest email when there are no topics."""
        self.make_post('first', 'my message 1')
        send_email.send_digest_email('foo@example.com', 1)
        self.fail()

    def make_post(self, post_id, message):
        """Makes a test post."""
        post_key = posts.insert_post(
            self.shard.shard_id,
            post_id=post_id,
            archive_type=models.Post.CHAT,
            nickname='My name',
            user_id=self.user_id,
            body=message)
        posts.apply_posts(self.shard.shard_id)
        return post_key

    def testOneTopicNewPost(self):
        """Tests when a single topic has a new post."""
        login_id = presence.user_logged_in(self.shard.shard_id, self.user_id)
        login_record = models.LoginRecord.get_by_id(login_id)
        login_record.email_address = 'foo@example.com'
        login_record.put()

        topic_shard_id, _ = topics.start_topic(
            self.shard.shard_id, self.user_id, 'my-post-id', 'my name',
            'topic title', 'topic description')
        posts.apply_posts(self.shard.shard_id)

        self.make_post('first', 'my message 1')
        posts.apply_posts(topic_shard_id)

        send_email.send_digest_email('foo@example.com', 1)

        mail_stub = self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)
        message_list = mail_stub.get_sent_messages()
        self.assertEquals(1, len(message_list))
        message = message_list[0]
        print 'html %r' % message.html.payload
        print 'text %r' % message.body.payload


if __name__ == '__main__':
    unittest.main()
