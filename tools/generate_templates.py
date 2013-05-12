#!/usr/bin/env python
#
# Copyright 2013 Brett Slatkin
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Generates inline CSS style for email templates.

You must have lxml installed to use this.

On Mac OSX with brew's Python, do something like:

easy_install --install-dir=/usr/local/lib/python2.7/site-packages lxm

Otherwise, you can probably ignore the --install-dir flag.


PS: Normally I avoid easy_install and related tools, but lxml is actually a
good package and won't destroy the world.
"""

import os
import sys

sys.path.insert(0, 'cssutils/src')
sys.path.insert(0, 'inlinestyler')

from inlinestyler.utils import inline_css

TEMPLATES_PATH = '../frontend/templates/'


for input_name in os.listdir(TEMPLATES_PATH):
    if not input_name.endswith('email_input.html'):
        continue

    input_path = os.path.join(TEMPLATES_PATH, input_name)
    output_path = input_path.replace('email_input.html', 'email_output.html')

    print 'Processing %s into %s' % (input_path, output_path)
    input_template = open(input_path).read()
    output_data = inline_css(input_template)
    open(output_path, 'w').write(output_data)
