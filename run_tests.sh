#!/bin/bash
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

ALL_TESTS="$1"
CRYPTOLIB=`ls -d pycrypto/build/lib.*`
DEV_APPSERVER=$(readlink `which dev_appserver.py`)
APP_ENGINE=$(dirname $DEV_APPSERVER)

cd backend

if [ -z "$ALL_TESTS" ]; then
    ALL_TESTS=$(find tests -name '*_test.py')
fi

for testpath in $ALL_TESTS; do
  echo "Running $testpath"
    PYTHONPATH=backend:$APP_ENGINE:$APP_ENGINE/lib:$APP_ENGINE/lib/django-1.4:$CRYPTOLIB:$PYTHONPATH \
    python -c "import dev_appserver, os; dev_appserver.fix_sys_path(); \
        os.environ['APPENGINE_RUNTIME'] = 'python27'; \
        dev_appserver.run_file('$testpath', globals(), 'tests');"
done
