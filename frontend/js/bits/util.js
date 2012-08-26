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
 * @fileoverview Common utility functions.
 */

goog.provide('bits.util');


/**
 * Regular expression used to match links.
 *
 * @type {RegExp}
 * @private
 * @const
 */
bits.util.LINK_RE_ = /(http(s?):\/\/[^ '"\)\(]+)/g;


/**
 * Replaces the links in the given text with a substitution string.
 * @param {string} text Text that may contain links.
 * @param {string} sub What to use as a replacement. May use '$1' to refer
 *   to the link that was matched.
 * @return {string} The rewritten string.
 */
bits.util.rewriteLink = function(text, sub) {
  return text.replace(bits.util.LINK_RE_, sub);
};
