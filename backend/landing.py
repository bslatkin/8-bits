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

"""Landing pages and chatroom renderer."""

import json
import xml.sax.saxutils

# Local libs
import base
import config
import models
import ndb


class LandingHandler(base.BaseHandler):
    """Renders the landing page."""

    def handle_request(self):
        # Treat xyz.example.com/the same as www.example.com/chat/xyz
        host_parts = self.request.host.split('.')
        if len(host_parts) > 2 and host_parts[0] != 'www':
            handler = ChatroomHandler()
            handler.initialize(self.request, self.response)
            return handler.get(host_parts[0])

        self.render('landing.html', dict(page_name='landing'))


class TermsHandler(base.BaseHandler):
    """Renders the terms of service page."""

    def handle_request(self):
        self.render('terms.html', dict(page_name='terms'))


class CreateChatroomHandler(base.BaseHandler):
    """Creates a new chatroom URL and redirects the user to it."""

    def handle_request(self):
        shard_id = None
        while True:
            def txn():
                shard_id = models.human_uuid()
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

        # For dev_appserver use the relative path. Otherwise use a sub-domain.
        if config.is_dev_appserver:
            self.redirect('/chat/' + shard_id)
        else:
            host_parts = self.request.host.split('.', 1)
            target_url = '%s://%s.%s/' % (
                self.request.scheme, shard_id, host_parts[1])
            self.redirect(target_url)


class ChatroomHandler(base.BaseHandler):
    """Renders a specific chatroom with the given shard ID."""

    def handle_request(self, shard_id):
        shard = models.Shard.get_by_id(shard_id)
        if not shard:
            # If the shard doesn't exist, then just create it. Makes it
            # ridiculously easy for people to create a new chat with the name
            # of their choice.
            def txn():
                shard = models.Shard.get_by_id(
                    shard_id, use_cache=False, use_memcache=False)
                if not shard:
                    shard = models.Shard(id=shard_id)
                    shard.put()
                return shard

            shard = ndb.transaction(txn)

        # Do not allow users to directly access topic shards.
        if shard.root_shard:
            # TODO(bslatkin): Make this pretty.
            self.response.set_status(404)
            return

        nickname = 'Anonymous'
        email_address = ''
        first_login = True
        must_accept_terms = True
        sounds_enabled = True

        if 'shards' in self.session:
            # TODO(bslatkin): Reuse presence code here.
            user_id = self.session['shards'].get(shard_id)
            if user_id:
                login_record = models.LoginRecord.get_by_id(user_id)
                if login_record and login_record.shard_id == shard_id:
                    email_address = login_record.email_address
                    nickname = login_record.nickname
                    first_login = False
                    must_accept_terms = bool(
                        login_record.accepted_terms_version !=
                        config.terms_version)
                    sounds_enabled = login_record.sounds_enabled

        context = {
            'email_address': email_address or '',
            'first_login': first_login,
            'must_accept_terms': must_accept_terms,
            'nickname': xml.sax.saxutils.unescape(nickname),
            'page_name': 'chatroom',
            'shard_id': shard_id,
            'short_url': self.request.path_url,
            'sounds_enabled': sounds_enabled,
            'xsrf_token': self.session['xsrf_token'],
        }
        context['params'] = json.dumps(context)

        self.render('chatroom.html', context)


ROUTES = [
    (r'/', LandingHandler),
    (r'/create', CreateChatroomHandler),
    (r'/terms', TermsHandler),
    (r'/chat/([a-zA-Z0-9-]{1,100})', ChatroomHandler)
]
