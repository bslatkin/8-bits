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
goog.require('goog.dom.ViewportSizeMonitor');
goog.require('goog.events.KeyCodes');
goog.require('goog.math.Size');
goog.require('goog.ui.Component');
goog.require('goog.ui.LabelInput');
goog.require('goog.ui.SplitPane');
goog.require('goog.ui.SplitPane.Orientation');

goog.require('bits.posts.Post');
goog.require('bits.posts.PostContainer');
goog.require('bits.events');


bits.chatbox.ChatBox = function(shardId) {
  this.shardId = shardId;
  this.postContainer = new bits.posts.PostContainer(shardId);
  this.chatInput = new goog.ui.LabelInput('Type chat message here');
  this.splitPane = new goog.ui.SplitPane(
        this.postContainer, this.chatInput,
        goog.ui.SplitPane.Orientation.VERTICAL);

  /**
   * Event handler for this object.
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);

  /**
   * Keyboard handler for this object. This object is created once the
   * component's DOM element is known.
   *
   * @type {goog.events.KeyHandler?}
   * @private
   */
  this.kh_ = null;

  /**
   * For watching the size of the parent container.
   * @type {goog.dom.ViewportSizeMonitor}
   * @private
   */
  this.sizeMonitor_ = new goog.dom.ViewportSizeMonitor();
  this.eh_.listen(
      this.sizeMonitor_, goog.events.EventType.RESIZE, this.resize_);
}
goog.inherits(bits.chatbox.ChatBox, goog.ui.Component);


/**
 * Creates an initial DOM representation for the component.
 */
bits.chatbox.ChatBox.prototype.createDom = function() {
  this.decorateInternal(this.dom_.createDom('div', 'bits-chatbox'));
};


/**
 * Decorates an existing HTML DIV element as a PostContainer.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.chatbox.ChatBox.prototype.decorateInternal = function(element) {
  bits.chatbox.ChatBox.superClass_.decorateInternal.call(this, element);

  var element = this.getElement();

  var postElem = goog.dom.getElementByClass('bits-post-container', element);
  if (!postElem) {
    postElem = this.dom_.createDom('div', 'bits-post-container');
  }
  this.postContainer.decorate(postElem);

  var inputElem = goog.dom.getElementByClass('bits-chat-input', element);
  if (!inputElem) {
    inputElem = this.dom_.createDom('div', 'bits-chat-input');
  }
  this.chatInput.decorate(inputElem);

  this.splitPane.decorate(element);
  this.splitPane.setContinuousResize(true);
  this.splitPane.setHandleSize(6);
  // this.splitPane.setSize(new goog.math.Size(400, 200));

  this.kh_ = new goog.events.KeyHandler(this.chatInput.getElement());
  this.eh_.listen(this.kh_, goog.events.KeyHandler.EventType.KEY, this.onKey_);
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
 * Called when component's element is known to be in the document.
 */
bits.chatbox.ChatBox.prototype.enterDocument = function() {
  bits.chatbox.ChatBox.superClass_.enterDocument.call(this);
};


/**
 * Called when component's element is known to have been removed from the
 * document.
 */
bits.chatbox.ChatBox.prototype.exitDocument = function() {
  bits.chatbox.ChatBox.superClass_.exitDocument.call(this);
};


/**
 * Fired when user presses a key while the DIV has focus.
 * @param {goog.events.Event} event The key event.
 * @private
 */
bits.chatbox.ChatBox.prototype.onKey_ = function(event) {
  if (event.keyCode == goog.events.KeyCodes.ENTER) {
    var chatText = goog.dom.forms.getValue(this.chatInput.getElement());
    bits.events.PubSub.publish(
        this.shardId, bits.events.EventType.SubmitPost,
        {
          archiveType: 'chat',
          body: chatText
        });

    // TODO: Filter out new lines, HTML, etc.
    goog.dom.forms.setValue(this.chatInput.getElement(), '');
    event.preventDefault();
  }
};


/**
 * Resize this element to fill its parent container. Will keep the chatbox
 * part of the splitpane the same size.
 * private
 */
bits.chatbox.ChatBox.prototype.resize_ = function() {
  var firstSize = this.splitPane.getFirstComponentSize();

  var parentSize = goog.style.getBorderBoxSize(this.getElement().parentNode);
  this.splitPane.setSize(
      new goog.math.Size(parentSize.width, parentSize.height));

  // todo make the split pane stay the same distance from the bottom
  // there's already code in splitpane to calculate the heights here
};
