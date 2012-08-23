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
 * @fileoverview Chatbox splitpane view.
 */

goog.provide('bits.chatbox.ChatBox');

goog.require('goog.dom');
goog.require('goog.dom.classes');
goog.require('goog.dom.forms');
goog.require('goog.events.KeyCodes');
goog.require('goog.math.Size');
goog.require('goog.string');
goog.require('goog.ui.Component');
goog.require('goog.ui.LabelInput');

goog.require('bits.events');
goog.require('bits.posts.PostContainer');


/**
 * Creates a new ChatBox.
 *
 * @param {string} Shard ID for this chatbox.
 * @constructor
 */
bits.chatbox.ChatBox = function(shardId) {
  goog.base(this);

  /**
   * @type {string}
   * @private
   */
  this.shardId_ = shardId;

  /**
   * @type {bits.posts.PostContainer}
   * @private
   */
  this.postContainer_ = new bits.posts.PostContainer(shardId);

  /**
   * @type {goog.ui.LabelInput}
   * @private
   */
  this.chatInput_ = new goog.ui.LabelInput(
      'Type chat messages here');

  /**
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);

  /**
   * @type {goog.events.KeyHandler?}
   * @private
   */
  this.kh_ = null;
}
goog.inherits(bits.chatbox.ChatBox, goog.ui.Component);


/**
 * Height of the chat input box, by default.
 * @type {number}
 */
bits.chatbox.ChatBox.INPUT_DEFAULT_HEIGHT = 100;


/**
 * Decorates an existing HTML DIV element as a ChatBox.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.chatbox.ChatBox.prototype.decorateInternal = function(element) {
  bits.chatbox.ChatBox.superClass_.decorateInternal.call(this, element);

  var element = this.getElement();

  var postElem = goog.dom.getElementByClass('bits-posts-scrollable', element);
  this.postContainer_.decorate(postElem);

  var inputElem = goog.dom.getElementByClass('bits-chat-input', element);
  this.chatInput_.decorate(inputElem);
};


/**
 * Disposes of the component.
 */
bits.chatbox.ChatBox.prototype.disposeInternal = function() {
  bits.chatbox.ChatBox.superClass_.disposeInternal.call(this);
  this.eh_.dispose();
  if (this.kh_) {
    this.kh_.dispose();
  }
};


/**
 * Called when the component's is in the document.
 */
bits.chatbox.ChatBox.prototype.enterDocument = function() {
  bits.chatbox.ChatBox.superClass_.enterDocument.call(this);

  this.kh_ = new goog.events.KeyHandler(this.chatInput_.getElement());
  this.eh_.listen(this.kh_, goog.events.KeyHandler.EventType.KEY, this.onKey_);
};


/**
 * Called when component's element is removed from the document.
 */
bits.chatbox.ChatBox.prototype.exitDocument = function() {
  bits.chatbox.ChatBox.superClass_.exitDocument.call(this);
};


/**
 * Fired when user presses a key in the chatbox.
 * @param {goog.events.Event} event Key event.
 * @private
 */
bits.chatbox.ChatBox.prototype.onKey_ = function(event) {
  if (event.keyCode == goog.events.KeyCodes.ENTER) {
    event.preventDefault();

    var chatText = goog.string.trim(
        goog.dom.forms.getValue(this.chatInput_.getElement()));

    // TODO(bslatkin): Actually show a warning to the user about this.
    if (!chatText || chatText > 4096) {
      return;
    }

    bits.events.PubSub.publish(
        this.shardId_, bits.events.EventType.SubmitPost,
        {
          'archiveType': 'chat',
          'body': chatText
        });

    goog.dom.forms.setValue(this.chatInput_.getElement(), '');
  }
};


/**
 * Sets this chatbox's input field as focused for keyboard input.
 */
bits.chatbox.ChatBox.prototype.focusAndSelect = function() {
  this.chatInput_.focusAndSelect();
};
