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
goog.require('goog.string');
goog.require('goog.style');
goog.require('goog.ui.Dialog');
goog.require('goog.ui.Dialog.ButtonSet');
goog.require('goog.ui.Dialog.DefaultButtonKeys');
goog.require('goog.ui.Component');

goog.require('bits.events');


/**
 * Creates a settings dialog.
 * @param {string} shardId ID of the shard this dialog is for.
 * @param {boolean} acceptedTerms Whether the user has already accepted terms.
 * @extends goog.ui.Component
 * @constructor
 */
bits.settings.SettingsDialog = function(shardId, acceptedTerms) {
  goog.base(this);

  this.shardId_ = shardId;

  this.dialog_ = new goog.ui.Dialog();
  this.dialog_.setHasTitleCloseButton(false);
  this.dialog_.setDraggable(false);
  this.dialog_.setVisible(false);

  /**
   * @type {?Element}
   * @private
   */
  this.emailEl_ = null;

  /**
   * @type {?Element}
   * @private
   */
  this.nicknameEl_ = null;

  /**
   * @type {?Element}
   * @private
   */
  this.soundsEnabledEl_ = null;

  /**
   * @type {?Element}
   * @private
   */
  this.termsEl_ = null;

  /**
   * @type {boolean}
   * private
   */
  this.acceptedTerms_ = acceptedTerms;

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
};
goog.inherits(bits.settings.SettingsDialog, goog.ui.Component);


/**
 * Accept the terms of service button.
 * @type {!{key: string, caption: string}}
 */
bits.settings.SettingsDialog.AGREE = {
  key: goog.ui.Dialog.DefaultButtonKeys.OK,
  caption: 'Agree'
};


/**
 * Decline the terms of service button.
 * @type {!{key: string, caption: string}}
 */
bits.settings.SettingsDialog.DECLINE = {
  key: 'decline',
  caption: 'Decline'
};


/**
 * Decorates an existing HTML DIV element as a PostContainer.
 *
 * @param {Element} element The DIV element to decorate.
 */
bits.settings.SettingsDialog.prototype.decorateInternal = function(element) {
  bits.settings.SettingsDialog.superClass_.decorateInternal.call(
      this, element);
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

  var element = this.getElement();

  this.emailEl_ = goog.dom.getElement('setting-email-address');
  this.nicknameEl_ = goog.dom.getElement('setting-nickname');
  this.soundsEnabledEl_ = goog.dom.getElement('setting-sounds-enabled');
  this.termsEl_ = goog.dom.getElement('settings-terms');

  goog.style.setStyle(element, 'display', undefined);
  this.dialog_.getContentElement().appendChild(element);

  this.eh_.listen(
      this.sizeMonitor_, goog.events.EventType.RESIZE,
      goog.bind(this.dialog_.reposition, this.dialog_));

  this.eh_.listen(
      this.dialog_, goog.ui.Dialog.EventType.SELECT,
      this.handleDialogSelect_);

  bits.events.PubSub.subscribe(
      this.shardId_, bits.events.EventType.ShowSettingsDialog,
      goog.bind(this.setVisible, this, true));
};


/**
 * Called when component's element is known to have been removed from the
 * document.
 */
bits.settings.SettingsDialog.prototype.exitDocument = function() {
  bits.settings.SettingsDialog.superClass_.exitDocument.call(this);

  goog.style.setStyle(this.getElement(), 'display', 'none');
  document.body.appendChild(this.getElement());
};


bits.settings.SettingsDialog.prototype.handleDialogSelect_ = function(e) {
  if (e.key == goog.ui.Dialog.DefaultButtonKeys.OK) {
    var emailAddress = goog.string.trim(
        /** @type {string} */ (goog.dom.forms.getValue(this.emailEl_)));
    var nickname = goog.string.trim(
        /** @type {string} */ (goog.dom.forms.getValue(this.nicknameEl_)));
    var soundsEnabled = goog.dom.forms.getValue(this.soundsEnabledEl_) == 'on';

    // TODO(bslatkin): Show a error message to users about invalid nicknames.
    if (!nickname || nickname.length > 32) {
      e.preventDefault();
      e.stopPropagation();
      return;
    }

    bits.events.PubSub.publish(
        this.shardId_, bits.events.EventType.SubmitPresenceChange,
        nickname,
        !this.acceptedTerms_,  // Only send param the first time.
        soundsEnabled,
        emailAddress);

    this.acceptedTerms_ = true;
  } else if (e.key == bits.settings.SettingsDialog.DECLINE.key) {
    // User has declined the terms of service.
    e.preventDefault();
    e.stopPropagation();
    window.location.href = '/';
  }
};


/**
 * Sets the dialog to visible.
 * @param {boolean} isVisible What the new state should be.
 */
bits.settings.SettingsDialog.prototype.setVisible = function(isVisible) {
  if (isVisible && this.dialog_.isVisible()) {
    return
  }
  this.dialog_.setVisible(isVisible);
  if (isVisible) {
    if (!this.acceptedTerms_) {
      goog.dom.classes.add(this.dialog_.getElement(), 'bits-first-time');
      this.dialog_.setEscapeToCancel(false);

      var buttonSet = new goog.ui.Dialog.ButtonSet().
          addButton(bits.settings.SettingsDialog.AGREE, false).
          addButton(bits.settings.SettingsDialog.DECLINE, false, true);
      this.dialog_.setButtonSet(buttonSet);
    } else {
      goog.dom.classes.remove(this.dialog_.getElement(), 'bits-first-time');
      this.dialog_.setEscapeToCancel(true);
      this.dialog_.setButtonSet(goog.ui.Dialog.ButtonSet.OK_CANCEL);
    }

    this.dialog_.reposition();
    this.nicknameEl_.focus();
    this.nicknameEl_.select();
  }
};
