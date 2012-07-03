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
 * @fileoverview Chatroom settings dialog.
 */

goog.provide('bits.settings.SettingsDialog');

goog.require('goog.dom');
goog.require('goog.dom.forms');
goog.require('goog.dom.ViewportSizeMonitor');
goog.require('goog.style');
goog.require('goog.ui.Dialog');
goog.require('goog.ui.Dialog.ButtonSet');
goog.require('goog.ui.Dialog.DefaultButtonKeys');
goog.require('goog.ui.Component');

goog.require('bits.events');


bits.settings.SettingsDialog = function(shardId) {
  goog.base(this);

  this.shardId_ = shardId;

  this.dialog_ = new goog.ui.Dialog();
  this.dialog_.setButtonSet(goog.ui.Dialog.ButtonSet.OK_CANCEL);
  this.dialog_.setTitle('Update your look');
  this.dialog_.setEscapeToCancel(true);
  this.dialog_.setHasTitleCloseButton(false);
  this.dialog_.setVisible(true);
  this.dialog_.setDraggable(false);

  this.interiorEl_ = null;

  this.nicknameEl_ = null;

  /**
   * Event handler for this object.
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);

  /**
   * For watching the size of the parent container.
   * @type {goog.dom.ViewportSizeMonitor}
   * @private
   */
  this.sizeMonitor_ = new goog.dom.ViewportSizeMonitor();
}
goog.inherits(bits.settings.SettingsDialog, goog.ui.Component);


/**
 * Creates an initial DOM representation for the component.
 */
bits.settings.SettingsDialog.prototype.createDom = function() {
  this.decorateInternal(this.dom_.createDom('div', 'bits-dialog'));
};


/**
 * Decorates an existing HTML DIV element as a PostContainer.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.settings.SettingsDialog.prototype.decorateInternal = function(element) {
  bits.settings.SettingsDialog.superClass_.decorateInternal.call(this, element);
};


/**
 * Disposes of the component.
 */
bits.settings.SettingsDialog.prototype.disposeInternal = function() {
  bits.settings.SettingsDialog.superClass_.disposeInternal.call(this);
  this.eh_.dispose();
};


/**
 * Called when component's element is known to be in the document.
 */
bits.settings.SettingsDialog.prototype.enterDocument = function() {
  bits.settings.SettingsDialog.superClass_.enterDocument.call(this);

  this.interiorEl_ = goog.dom.getElement('settings-dialog');
  this.nicknameEl_ = goog.dom.getElement('setting-nickname');

  goog.style.setStyle('display', null);
  this.dialog_.getContentElement().appendChild(this.interiorEl_);
  this.dialog_.reposition();

  this.eh_.listen(
      this.sizeMonitor_, goog.events.EventType.RESIZE,
      goog.bind(this.dialog_.reposition, this.dialog_));

  this.eh_.listen(
      this.dialog_, goog.ui.Dialog.EventType.SELECT,
      this.handleDialogSelect_);
};


/**
 * Called when component's element is known to have been removed from the
 * document.
 */
bits.settings.SettingsDialog.prototype.exitDocument = function() {
  bits.settings.SettingsDialog.superClass_.exitDocument.call(this);

  goog.style.setStyle('display', 'none');
  document.body.appendChild(this.interiorEl_);
};


bits.settings.SettingsDialog.prototype.handleDialogSelect_ = function(e) {
  if (e.key == goog.ui.Dialog.DefaultButtonKeys.OK) {
    bits.events.PubSub.publish(
        this.shardId_, bits.events.EventType.SubmitPresenceChange,
        {
          nickname: goog.dom.forms.getValue(this.nicknameEl_)
        });
  }
};


bits.settings.SettingsDialog.prototype.setVisible = function(isVisible) {
  this.dialog_.setVisible(isVisible);
};
