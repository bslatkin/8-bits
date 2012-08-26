// Copyright 2010 Brett Slatkin, Nathan Naze
// 
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
// 
//     http://www.apache.org/licenses/LICENSE-2.0
// 
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * @fileoverview Main startup file for 8-bits.
 */

goog.provide('bits.startup');

goog.require('goog.dom');
goog.require('goog.debug.Console');
goog.require('goog.debug.Logger');
goog.require('goog.json');
goog.require('goog.ui.Dialog');
goog.require('goog.ui.Dialog.ButtonSet');

goog.require('bits.connection.Connection');
goog.require('bits.chatbox.ChatBox');
goog.require('bits.footer.FooterBar');
goog.require('bits.notifier.Notifier');
goog.require('bits.settings.SettingsDialog');
goog.require('bits.shorturl.ShortUrlDialog');
goog.require('bits.topics.TopicPrompt');


bits.startup = function(params) {
  var shardId = params.shard_id;
  var nickname = params.nickname;
  var firstLogin = params.first_login;
  var mustAcceptTerms = params.must_accept_terms;
  var soundsEnabled = params.sounds_enabled;

  var c = new goog.debug.Console();
  c.setCapturing(true);

  var logger = goog.debug.Logger.getLogger('bits.startup');
  logger.info('Starting up with params: ' + goog.json.serialize(params));

  // Set up all the various UI components.
  var connection = new bits.connection.Connection(
      shardId, nickname, soundsEnabled);

  var chatbox = new bits.chatbox.ChatBox(shardId);
  chatbox.decorate(goog.dom.getElement('chatbox'));

  var topicPrompt = new bits.topics.TopicPrompt(shardId);
  topicPrompt.decorate(goog.dom.getElement('topic-prompt'));

  var footer = new bits.footer.FooterBar(shardId);
  footer.decorate(goog.dom.getElement('footer-bar'));

  var settings = new bits.settings.SettingsDialog(shardId, !mustAcceptTerms);
  settings.decorate(goog.dom.getElement('settings-dialog'));

  var shortUrlDialog = new bits.shorturl.ShortUrlDialog(shardId);
  shortUrlDialog.decorate(goog.dom.getElement('link-dialog'));

  var notifier = new bits.notifier.Notifier(
      shardId, nickname, soundsEnabled);

  // Now do initial actions.
  if (firstLogin || mustAcceptTerms) {
    settings.setVisible(true);
  } else {
    connection.login();
    // TODO(bslatkin): Do this after ConnectionReestablishing events, which
    // will include the re-logins and the moment after the user first closes
    // the presence dialog.
    chatbox.focusAndSelect();
  }
};


goog.exportSymbol('bits.startup', bits.startup);
