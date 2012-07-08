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
 * @fileoverview Dialog for copying a short URL for a chatroom.
 */

goog.provide('bits.shorturl.ShortUrlDialog');

goog.require('goog.dom');
goog.require('goog.dom.forms');
goog.require('goog.dom.ViewportSizeMonitor');
goog.require('goog.style');
goog.require('goog.ui.Dialog');
goog.require('goog.ui.Dialog.ButtonSet');
goog.require('goog.ui.Component');

goog.require('bits.events');


/**
 * Constructs the short URL dialog.
 * @param {string} shardId Shard for this short URL dialog.
 * @constructor
 */
bits.shorturl.ShortUrlDialog = function(shardId) {
  goog.base(this);

  /**
   * @type {string}
   * @private
   */
  this.shardId_ = shardId;

  /**
   * @type {goog.ui.Dialog}
   * @private
   */
  this.dialog_ = new goog.ui.Dialog();
  this.dialog_.setButtonSet(goog.ui.Dialog.ButtonSet.OK);
  this.dialog_.setEscapeToCancel(true);
  this.dialog_.setHasTitleCloseButton(false);
  this.dialog_.setDraggable(false);
  this.dialog_.setVisible(false);

  /**
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);

  /**
   * @type {goog.dom.ViewportSizeMonitor}
   * @private
   */
  this.sizeMonitor_ = new goog.dom.ViewportSizeMonitor();
}
goog.inherits(bits.shorturl.ShortUrlDialog, goog.ui.Component);


/**
 * Decorates an existing HTML DIV element as a PostContainer.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.shorturl.ShortUrlDialog.prototype.decorateInternal = function(element) {
  bits.shorturl.ShortUrlDialog.superClass_.decorateInternal.call(this, element);
};


/**
 * Disposes of the component.
 */
bits.shorturl.ShortUrlDialog.prototype.disposeInternal = function() {
  bits.shorturl.ShortUrlDialog.superClass_.disposeInternal.call(this);
  this.eh_.dispose();
};


/**
 * Called when component's element is known to be in the document.
 */
bits.shorturl.ShortUrlDialog.prototype.enterDocument = function() {
  bits.shorturl.ShortUrlDialog.superClass_.enterDocument.call(this);

  var element = this.getElement();
  goog.style.setStyle(element, 'display', null);
  this.dialog_.getContentElement().appendChild(element);

  this.eh_.listen(
      this.sizeMonitor_, goog.events.EventType.RESIZE,
      goog.bind(this.dialog_.reposition, this.dialog_));

  bits.events.PubSub.subscribe(
      this.shardId_, bits.events.EventType.ShowShortUrlDialog,
      goog.bind(this.setVisible_, this, true));
};


/**
 * Called when component's element is known to have been removed from the
 * document.
 */
bits.shorturl.ShortUrlDialog.prototype.exitDocument = function() {
  bits.shorturl.ShortUrlDialog.superClass_.exitDocument.call(this);

  goog.style.setStyle(this.getElement(), 'display', 'none');
  document.body.appendChild(this.getElement());
};


/**
 * Sets if this dialog is visible or not.
 * @param {boolean} isVisible Whether to make this dialog visible.
 * @private
 */
bits.shorturl.ShortUrlDialog.prototype.setVisible_ = function(isVisible) {
  if (isVisible && this.dialog_.isVisible()) {
    return
  }
  this.dialog_.setVisible(isVisible);
  if (isVisible) {
    this.dialog_.reposition();
    goog.dom.getElement('link-shorturl', this.getElement()).focus();
  }
};
