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
 * @fileoverview Responsible for notifying the user about new posts using
 * icons, sounds, push notifications, etc.
 */

goog.provide('bits.notifier.Notifier');

goog.require('goog.dom');
goog.require('goog.events');
goog.require('goog.style');

goog.require('bits.events');


/**
 * Constructs a new Notifier object.
 * @param {string} shardId ID of the shard to notify for.
 * @constructor
 */
bits.notifier.Notifier = function(shardId) {
  goog.base(this);

  this.shardId_ = shardId;

  bits.events.PubSub.subscribe(
      this.shardId_, bits.events.EventType.ShowSettingsDialog);

}
goog.inherits(bits.notifier.Notifier, goog.Disposable);


/**
 * Disposes of the object.
 */
bits.notifier.Notifier.prototype.disposeInternal = function() {
  bits.notifier.Notifier.superClass_.disposeInternal.call(this);
  this.shardId_ = null;
};


bits.notifier.Notifier.prototype.handleClickEdit_ = function(e) {
  bits.events.PubSub.publish(
      this.shardId_, bits.events.EventType.ShowSettingsDialog);
};

