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
 * @fileoverview Landing page script for 8-bits.
 */

goog.provide('bits.landing');

goog.require('goog.dom');
goog.require('goog.events');


bits.landing = function() {
  var createForm = goog.dom.getElement('create-form');
  var createEl = goog.dom.getElementByClass('landing-create-image-c');
  goog.events.listen(
      createEl, goog.events.EventType.CLICK,
      function() { createForm.submit(); });
};


goog.exportSymbol('bits.landing', bits.landing);
