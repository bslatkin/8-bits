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

goog.require('goog.Timer');
goog.require('goog.dom');
goog.require('goog.dom.ViewportSizeMonitor');
goog.require('goog.dom.classes');
goog.require('goog.events');
goog.require('goog.style');
goog.require('goog.ui.Component');
goog.require('goog.ui.Slider');


/**
 * Creates a new scrollbar.
 * @extends goog.ui.Slider
 * @constructor
 */
bits.ui.Scrollbar = function() {
  goog.base(this);

  this.setOrientation(goog.ui.Slider.Orientation.VERTICAL);
  this.setMoveToPointEnabled(true);
  this.setUnitIncrement(8);

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

  /**
   * @type {goog.dom.ViewportSizeMonitor}
   * @private
   */
  this.sizeMonitor_ = new goog.dom.ViewportSizeMonitor();

  /**
   * @type {goog.Timer}
   * @private
   */
  this.deactiveTimer_ = new goog.Timer(500);
};
goog.inherits(bits.ui.Scrollbar, goog.ui.Slider);


/**
 * Sets the target that will be scrolled by this scrollbar.
 *
 * @param {Element} target Target to scroll.
 */
bits.ui.Scrollbar.prototype.setTarget = function(target) {
  this.target_ = target;
  // goog.style.getScrollbarWidth returns 0px on Mac OS X 10.8 Chrome, causing
  // the Mac scrollbar to keep showing. Just setting a really high padding
  // here seems to solve the issue in general since the container of the
  // scrollbar will always have a fixed width and hidden overflow.
  this.target_.style.paddingRight = '40px';
};


/**
 * Decorates an existing HTML DIV element as a scroller.
 *
 * @param {Element} element The DIV element to decorate.
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
    this.sizeMonitor_, goog.events.EventType.RESIZE, this.updateFromTarget_);

  this.eh_.listen(
      this.deactiveTimer_, goog.Timer.TICK, this.handleDeactivate_);

  this.eh_.listen(
      this.target_, goog.events.EventType.SCROLL, this.updateFromTarget_);

  this.eh_.listen(
      this, goog.ui.Component.EventType.CHANGE, this.updateFromSlider_);

  this.updateFromTarget_();
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
  var adjustedHeight = this.target_.scrollHeight - targetSize.height;
  var ratio = this.target_.scrollHeight / targetSize.height;

  // Must set thumb height before calling setValue or else the calculation
  // comes out wrong on initialization.
  var thumbHeight = Math.max(20, targetSize.height / ratio);
  goog.style.setHeight(this.getValueThumb(), thumbHeight);

  this.setMinimum(0);
  this.setMaximum(adjustedHeight);

  var value = adjustedHeight - this.target_.scrollTop;
  this.setValue(value);

  // If we're at the very top or the bottom, then don't activate. This
  // prevents the scrollbar from flashing when a new item is added to the
  // container and it auto-scrolls to bring that item into view.
  if (this.target_.scrollTop == 0 ||
      this.target_.scrollTop == adjustedHeight) {
    return;
  }

  this.deactiveTimer_.stop();
  this.deactiveTimer_.start();
  goog.dom.classes.add(this.getElement(), 'active');
};


/**
 * Updates the target's scroll offset to match the current slider position.
 * @param {goog.events.Event} e Scroll event.
 * @private
 */
bits.ui.Scrollbar.prototype.updateFromSlider_ = function(e) {
  var targetSize = goog.style.getSize(this.target_);
  var adjustedHeight = this.target_.scrollHeight - targetSize.height;
  this.target_.scrollTop = adjustedHeight - this.getValue();
};


/**
 * Handles when interaction with the scrollbar has finished.
 * @private
 */
bits.ui.Scrollbar.prototype.handleDeactivate_ = function(e) {
  this.deactiveTimer_.stop();
  goog.dom.classes.remove(this.getElement(), 'active');
};
