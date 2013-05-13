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
import time
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

        mail_stub = self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)
        message_list = mail_stub.get_sent_messages()
        self.assertEquals(0, len(message_list))

    def login_user(self, shard_id=None):
        """Logs in the user."""
        if shard_id is None:
            shard_id = self.shard.shard_id

        login_id = presence.user_logged_in(shard_id, self.user_id)
        login_record = models.LoginRecord.get_by_id(login_id)
        login_record.email_address = 'foo@example.com'
        login_record.put()

    def make_post(self, post_id, message, shard_id=None):
        """Makes a test post."""
        if shard_id is None:
            shard_id = self.shard.shard_id

        post_key = posts.insert_post(
            shard_id,
            post_id=post_id,
            archive_type=models.Post.CHAT,
            nickname='My name',
            user_id=self.user_id,
            body=message)
        posts.apply_posts(shard_id)
        return post_key

    def start_topic(self, url, nickname, description, shard_id=None):
        """Makes a test topic."""
        if shard_id is None:
            shard_id = self.shard.shard_id

        topic_shard_id, _ = topics.start_topic(
            shard_id,
            self.user_id,
            'my-post-id-%f' % time.time(),
            nickname,
            url,
            description)
        posts.apply_posts(shard_id)
        posts.apply_posts(topic_shard_id)
        return topic_shard_id

    def get_email(self, count=1, index=0):
        """Gets a sent email, saves it to the /tmp directory for previewing."""
        mail_stub = self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)
        message_list = mail_stub.get_sent_messages()
        self.assertEquals(count, len(message_list))
        message = message_list[index]

        html_content = message.html.payload
        text_content = message.body.payload

        output_path = '/tmp/test_email_output_%s' % self.id()
        print 'Writing output to', output_path

        open(output_path + '.html', 'w').write(html_content)
        open(output_path + '.txt', 'w').write(text_content)

        return message

    def testRootShardOnly(self):
        """Tests when only the root shard has new data."""
        self.login_user()
        self.make_post('first', 'my message 1')
        send_email.send_digest_email('foo@example.com', 1)

        message = self.get_email()

        self.assertEquals('8-bits of ephemera <test-app.appspotmail.com>',
                          message.sender)
        self.assertEquals("What's new: 1 topic, 1 update",
                          message.subject)

    def testMultipleRootShardsOnly(self):
        """Tests multiple root shards have new data with no topics."""
        shard1 = models.Shard(id='my-shard-1')
        shard1.put()
        shard2 = models.Shard(id='my-shard-2')
        shard2.put()

        self.login_user(shard1.shard_id)
        self.login_user(shard2.shard_id)

        self.make_post('first', 'my message 1', shard_id=shard1.shard_id)
        self.make_post('second', 'my message 2', shard_id=shard2.shard_id)

        send_email.send_digest_email('foo@example.com', 1)

        message = self.get_email()

        self.assertEquals('8-bits of ephemera <test-app.appspotmail.com>',
                          message.sender)
        self.assertEquals("What's new: 2 topics, 2 updates",
                          message.subject)

    def testOneTopicNewPost(self):
        """Tests when a single topic has a new post."""
        self.login_user()

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
        self.login_user()

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

        send_email.send_digest_email('foo@example.com', 1)

        mail_stub = self.testbed.get_stub(testbed.MAIL_SERVICE_NAME)
        message_list = mail_stub.get_sent_messages()
        self.assertEquals(1, len(message_list))  # One email, not two

    def testSecondDigestEmail(self):
        """Tests what the second digest email looks like."""
        self.login_user()

        topic_shard_id = self.start_topic(
            'http://www.example.com/path/is/here',
            'cilantro',
            'This is my long winded topic description that surely will '
            'bore you to tears')

        self.make_post('first', 'my message 1')
        self.make_post('second', 'my other message')
        self.make_post('third', 'message number 3')
        posts.apply_posts(topic_shard_id)

        send_email.send_digest_email('foo@example.com', 1)
        message = self.get_email(count=1, index=0)
        self.assertEquals('8-bits of ephemera <test-app.appspotmail.com>',
                          message.sender)
        self.assertEquals("What's new: 1 topic, 4 updates",
                          message.subject)

        topic_shard_id = self.start_topic(
            'http://www.example.com/this/is/another/topic',
            'lime',
            'Wow I never thought I would be starting my own topic')

        self.make_post('red', 'this is for a new topic')
        self.make_post('green', 'and will continue')
        posts.apply_posts(topic_shard_id)

        send_email.send_digest_email('foo@example.com', 2)

        message = self.get_email(count=2, index=1)

        self.assertEquals('8-bits of ephemera <test-app.appspotmail.com>',
                          message.sender)
        self.assertEquals("What's new: 1 topic, 3 updates",
                          message.subject)

    def testManyTopicsManyPosts(self):
        """Tests when many topics have many new posts."""
        self.login_user()

        topic_shard_id = self.start_topic(
            'http://www.example.com/path/is/here',
            'cilantro',
            'This is my long winded topic description that surely will '
            'bore you to tears')

        self.make_post('first', 'my message 1')
        self.make_post('second', 'my other message')
        self.make_post('third', 'message number 3')
        posts.apply_posts(topic_shard_id)

        topic_shard_id = self.start_topic(
            'http://www.example.com/this/is/another/topic',
            'lime',
            'Wow I never thought I would be starting my own topic')

        self.make_post('red', 'this is for a new topic')
        self.make_post('green', 'and will continue')
        posts.apply_posts(topic_shard_id)

        send_email.send_digest_email('foo@example.com', 1)

        message = self.get_email()

        self.assertEquals('8-bits of ephemera <test-app.appspotmail.com>',
                          message.sender)
        self.assertEquals("What's new: 2 topics, 7 updates",
                          message.subject)

    def testMultipleShards(self):
        """Tests when the user is part of multiple shards."""
        shard1 = models.Shard(id='my-shard-1')
        shard1.put()
        shard2 = models.Shard(id='my-shard-2')
        shard2.put()

        self.login_user('my-shard-1')
        self.login_user('my-shard-2')

        topic_id = self.start_topic(
            'http://example.com/1', 'peanut', 'hi there',
            shard_id='my-shard-1')
        self.make_post('first', 'my message here', shard_id='my-shard-1')
        posts.apply_posts(topic_id)

        topic_id = self.start_topic(
            'http://example.com/2', 'cashew', 'this is nuts!',
            shard_id='my-shard-2')
        self.make_post('second', 'my second here', shard_id='my-shard-2')
        self.make_post('third', 'my third here', shard_id='my-shard-2')
        posts.apply_posts(topic_id)

        send_email.send_digest_email('foo@example.com', 1)

        message = self.get_email()

        self.assertEquals('8-bits of ephemera <test-app.appspotmail.com>',
                          message.sender)
        self.assertEquals("What's new: 2 topics, 5 updates",
                          message.subject)


if __name__ == '__main__':
    unittest.main()
