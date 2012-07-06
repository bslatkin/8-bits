// Copyright 2012 Brett Slatkin
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
 * @fileoverview Chatroom footer bar.
 */

goog.provide('bits.footer.FooterBar');

goog.require('goog.dom');
goog.require('goog.style');
goog.require('goog.ui.Component');

goog.require('bits.events');


bits.footer.FooterBar = function(shardId) {
  goog.base(this);

  this.shardId_ = shardId;
  this.nicknameEl_ = null;

  /**
   * Event handler for this object.
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);
}
goog.inherits(bits.footer.FooterBar, goog.ui.Component);


/**
 * Decorates an existing HTML DIV element as a PostContainer.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.footer.FooterBar.prototype.decorateInternal = function(element) {
  bits.footer.FooterBar.superClass_.decorateInternal.call(this, element);
};


/**
 * Disposes of the component.
 */
bits.footer.FooterBar.prototype.disposeInternal = function() {
  bits.footer.FooterBar.superClass_.disposeInternal.call(this);
  this.eh_.dispose();
};


/**
 * Called when component's element is known to be in the document.
 */
bits.footer.FooterBar.prototype.enterDocument = function() {
  bits.footer.FooterBar.superClass_.enterDocument.call(this);

  this.nicknameEl_ = goog.dom.getElement('nickname-display');

  var editLink = goog.dom.getElement('nickname-change');
  this.eh_.listen(
      editLink, goog.events.EventType.CLICK,
      this.handleClickEdit_);

  var rosterLink = goog.dom.getElement('see-roster');
  this.eh_.listen(
      rosterLink, goog.events.EventType.CLICK,
      this.handleClickGetRoster_);

  bits.events.PubSub.subscribe(
    this.shardId_, bits.events.EventType.SubmitPresenceChange,
    goog.bind(this.handlePresenceChange_, this));
};


/**
 * Called when component's element is known to have been removed from the
 * document.
 */
bits.footer.FooterBar.prototype.exitDocument = function() {
  bits.footer.FooterBar.superClass_.exitDocument.call(this);
};


bits.footer.FooterBar.prototype.handleClickEdit_ = function(e) {
  e.preventDefault();
  e.stopPropagation();

  bits.events.PubSub.publish(
      this.shardId_, bits.events.EventType.ShowSettingsDialog);
};


bits.footer.FooterBar.prototype.handleClickGetRoster_ = function(e) {
  e.preventDefault();
  e.stopPropagation();

  bits.events.PubSub.publish(
      this.shardId_, bits.events.EventType.RequestRoster);
};


bits.footer.FooterBar.prototype.handlePresenceChange_ = function(data) {
  goog.dom.setTextContent(this.nicknameEl_, data.nickname);
};
