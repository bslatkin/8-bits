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
import random
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
        config.email_resource_host_prefix = 'http://localhost:8080'
        config.shard_url_template = 'http://localhost:8080/chat/%s'
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

    def start_topic(self, url, nickname, description):
        """Makes a test topic."""
        topic_shard_id, _ = topics.start_topic(
            self.shard.shard_id,
            self.user_id,
            'my-post-id-' % random.randint(),
            nickname,
            url,
            description)
        posts.apply_posts(self.shard.shard_id)
        return topic_shard_id

    def get_email(self):
        """Gets a sent email, saves it to the /tmp directory for previewing."""
        mail_stub = self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)
        message_list = mail_stub.get_sent_messages()
        self.assertEquals(1, len(message_list))
        message = message_list[0]

        html_content = message.html.payload
        text_content = message.body.payload

        output_path = '/tmp/test_email_output_%s' % self.id()
        print 'Writing output to', output_path

        open(output_path + '.html', 'w').write(html_content)
        open(output_path + '.txt', 'w').write(text_content)

        return message

    def testRootShardOnly(self):
        """Tests when only the root shard has new data."""
        self.fail()

    def testOneTopicNewPost(self):
        """Tests when a single topic has a new post."""
        login_id = presence.user_logged_in(self.shard.shard_id, self.user_id)
        login_record = models.LoginRecord.get_by_id(login_id)
        login_record.email_address = 'foo@example.com'
        login_record.put()

        topic_shard_id = self.start_topic(
            'http://www.example.com/path/is/here',
            'cilantro',
            'This is my long winded topic description that surely will '
            'bore you to tears')

        self.make_post('first', 'my message 1')
        posts.apply_posts(topic_shard_id)

        send_email.send_digest_email('foo@example.com', 1)

        message = self.get_email()

        self.assertEquals('8-bits of ephemera <test-app.appspotmail.com>',
                          message.sender)
        self.assertEquals("What's new: 1 topic, 2 updates",
                          message.subject)

    def testNotifyTwiceNoChanges(self):
        """Tests that notifying when there are no changes sends no email."""
        self.fail()

    def testSecondDigestEmail(self):
        """Tests what the second digest email looks like."""
        self.fail()

    def testManyTopicsManyPosts(self):
        """Tests when many topics have many new posts."""
        self.fail()

    def testManyUsers(self):
        """Tests when many users have participated."""
        self.fail()


if __name__ == '__main__':
    unittest.main()
