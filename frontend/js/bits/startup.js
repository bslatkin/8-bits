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
goog.require('goog.ui.Dialog');
goog.require('goog.ui.Dialog.ButtonSet');

goog.require('bits.connection.Connection');
goog.require('bits.chatbox.ChatBox');


bits.startup = function(shardId, nickname) {
  var c = new goog.debug.Console();
  c.setCapturing(true);

  var connection = new bits.connection.Connection(shardId, nickname);
  connection.login();

  var chatbox = new bits.chatbox.ChatBox(shardId);
  chatbox.decorate(goog.dom.getElement('chatbox'));

  // TODO: Move this to a separate class.
  var settingsDialog = new goog.ui.Dialog();
  settingsDialog.getContentElement().appendChild(
        goog.dom.getElement('settings-dialog'));
  settingsDialog.setButtonSet(goog.ui.Dialog.ButtonSet.OK_CANCEL);
  settingsDialog.setEscapeToCancel(true);
  settingsDialog.setHasTitleCloseButton(false);
  settingsDialog.setVisible(true);
  settingsDialog.setDraggable(false);
};


goog.exportSymbol('bits.startup', bits.startup);
