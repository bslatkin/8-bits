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
 * @fileoverview Custom scrollbar for scrollable containers.
 */

goog.provide('bits.ui.Scrollbar');

goog.require('goog.dom');
goog.require('goog.events');
goog.require('goog.style');
goog.require('goog.ui.Component');
goog.require('goog.ui.Slider');


/**
 * Creates a new scrollbar.
 *
 * @constructor
 */
bits.ui.Scrollbar = function() {
  goog.base(this);

  this.setOrientation(goog.ui.Slider.Orientation.VERTICAL);

  /**
   * @type {Element}
   * @private
   */
  this.target_ = null;

  /**
   * @type {goog.events.EventHandler}
   * @private
   */
  this.eh_ = new goog.events.EventHandler(this);
}
goog.inherits(bits.ui.Scrollbar, goog.ui.Slider);


/**
 * Sets the target that will be scrolled by this scrollbar.
 *
 * @param {Element} target Target to scroll.
 */
bits.ui.Scrollbar.prototype.setTarget = function(target) {
  this.target_ = target;
  this.updateFromTarget_();
};


/**
 * Decorates an existing HTML DIV element as a scroller.
 *
 * @param {HTMLElement} element The DIV element to decorate.
 */
bits.ui.Scrollbar.prototype.decorateInternal = function(element) {
  bits.ui.Scrollbar.superClass_.decorateInternal.call(this, element);
};


/**
 * Disposes of the component.
 */
bits.ui.Scrollbar.prototype.disposeInternal = function() {
  bits.ui.Scrollbar.superClass_.disposeInternal.call(this);
  this.eh_.dispose();
};


/**
 * Called when the component's is in the document.
 */
bits.ui.Scrollbar.prototype.enterDocument = function() {
  bits.ui.Scrollbar.superClass_.enterDocument.call(this);

  this.eh_.listen(
      this.target_, goog.events.EventType.SCROLL, this.updateFromTarget_);
  this.eh_.listen(
      this, goog.ui.Component.EventType.CHANGE, this.updateFromSlider_);
};


/**
 * Called when component's element is removed from the document.
 */
bits.ui.Scrollbar.prototype.exitDocument = function() {
  bits.ui.Scrollbar.superClass_.exitDocument.call(this);
};


/**
 * Updates the slider position to match the target's current scroll offset.
 * @private
 */
bits.ui.Scrollbar.prototype.updateFromTarget_ = function() {
  var targetSize = goog.style.getSize(this.target_);

  this.setMinimum(0);
  this.setMaximum(this.target_.scrollHeight - targetSize.height);
  this.setValue(
      this.target_.scrollHeight - this.target_.scrollTop - targetSize.height);
};


/**
 * Updates the target's scroll offset to match the current slider position.
 * @param {goog.events.Event} e Scroll event.
 * @private
 */
bits.ui.Scrollbar.prototype.updateFromSlider_ = function(e) {
  var targetSize = goog.style.getSize(this.target_);
  this.target_.scrollTop =
      this.target_.scrollHeight - this.getValue() - targetSize.height;
};
