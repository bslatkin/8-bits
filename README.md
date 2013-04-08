# 8-bits

Create a private stream with close friends. Only people who get the secret link from you can join it. Share silly websites, images, and stories. Be serious when you need to. It's like chat, but you can catch up on what you've missed. Each post is auto-deleted after ten days, fading like memories.

[Please click here for the live site](https://www.8-bits.us)

To contribute, please first sign the [Contributor License Agreement](https://docs.google.com/spreadsheet/viewform?formkey=dDkyUzJuVk0tT0RIR244cVBKWDdOWUE6MQ#gid=0) (generated by harmonyagreements.org).

Disclaimer: The source code and opinions expressed on this site belong to the
participants in the project, respectively, not to their employers or clients.


# Directions

You'll need Python 2.7 and the [App Engine SDK](https://developers.google.com/appengine/downloads).

Run this command to build PyCrypto. It's built locally so it won't pollute your global site-packages. Using Brew is fine too.

    cd pycrypto
    python setup.py build

You need some secret keys for the session cookie library and XSRF protection. Run this script once to generate them.

    make_secrets.sh

#### To run the app locally:

    ./run_server.sh

####  To see frontend tests:

    ./run_server.sh
    # Navigate to http://localhost:8080/tests/index.html

#### To compile the JS into a binary:

    ./gendepsfile.sh
    ./compile.sh
