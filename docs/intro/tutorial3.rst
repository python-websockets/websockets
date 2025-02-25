Part 3 - Deploy to the web
==========================

.. currentmodule:: websockets

.. admonition:: This is the third part of the tutorial.

    * In the :doc:`first part <tutorial1>`, you created a server and
      connected one browser; you could play if you shared the same browser.
    * In this :doc:`second part <tutorial2>`, you connected a second browser;
      you could play from different browsers on a local network.
    * In this :doc:`third part <tutorial3>`, you will deploy the game to the
      web; you can play from any browser connected to the Internet.

In the first and second parts of the tutorial, for local development, you ran
an HTTP server on ``http://localhost:8000/`` with:

.. code-block:: console

    $ python -m http.server

and a WebSocket server on ``ws://localhost:8001/`` with:

.. code-block:: console

    $ python app.py

Now you want to deploy these servers on the Internet. There's a vast range of
hosting providers to choose from. For the sake of simplicity, we'll rely on:

* `GitHub Pages`_ for the HTTP server;
* Koyeb_ for the WebSocket server.

.. _GitHub Pages: https://pages.github.com/
.. _Koyeb: https://www.koyeb.com/

Koyeb is a modern Platform as a Service provider whose free tier allows you to
run a web application, including a WebSocket server.

Commit project to git
---------------------

Perhaps you committed your work to git while you were progressing through the
tutorial. If you didn't, now is a good time, because GitHub and Koyeb offer
git-based deployment workflows.

Initialize a git repository:

.. code-block:: console

    $ git init -b main
    Initialized empty Git repository in websockets-tutorial/.git/
    $ git commit --allow-empty -m "Initial commit."
    [main (root-commit) 8195c1d] Initial commit.

Add all files and commit:

.. code-block:: console

    $ git add .
    $ git commit -m "Initial implementation of Connect Four game."
    [main 7f0b2c4] Initial implementation of Connect Four game.
     6 files changed, 500 insertions(+)
     create mode 100644 app.py
     create mode 100644 connect4.css
     create mode 100644 connect4.js
     create mode 100644 connect4.py
     create mode 100644 index.html
     create mode 100644 main.js

Sign up or log in to GitHub.

Create a new repository. Set the repository name to ``websockets-tutorial``,
the visibility to Public, and click **Create repository**.

Push your code to this repository. You must replace ``python-websockets`` by
your GitHub username in the following command:

.. code-block:: console

    $ git remote add origin git@github.com:python-websockets/websockets-tutorial.git
    $ git branch -M main
    $ git push -u origin main
    ...
    To github.com:python-websockets/websockets-tutorial.git
     * [new branch]      main -> main
    Branch 'main' set up to track remote branch 'main' from 'origin'.

Adapt the WebSocket server
--------------------------

Before you deploy the server, you must adapt it for Koyeb's environment. This
involves three small changes:

1. Koyeb provides the port on which the server should listen in the ``$PORT``
   environment variable.

2. Koyeb requires a health check to verify that the server is running. We'll add
   a HTTP health check.

3. Koyeb sends a ``SIGTERM`` signal when terminating the server. We'll catch it
   and trigger a clean exit.

Adapt the ``main()`` coroutine accordingly:

.. code-block:: python

    import http
    import os
    import signal

.. literalinclude:: ../../example/tutorial/step3/app.py
    :pyobject: health_check

.. literalinclude:: ../../example/tutorial/step3/app.py
    :pyobject: main

The ``process_request`` parameter of :func:`~asyncio.server.serve` is a callback
that runs for each request. When it returns an HTTP response, websockets sends
that response instead of opening a WebSocket connection. Here, requests to
``/healthz`` return an HTTP 200 status code.

``main()`` registers a signal handler that closes the server when receiving the
``SIGTERM`` signal. Then, it waits for the server to be closed. Additionally,
using :func:`~asyncio.server.serve` as a context manager ensures that the server
will always be closed cleanly, even if the program crashes.

Deploy the WebSocket server
---------------------------

Create a ``requirements.txt`` file with this content to install ``websockets``
when building the image:

.. literalinclude:: ../../example/tutorial/step3/requirements.txt
    :language: text

.. admonition:: Koyeb treats ``requirements.txt`` as a signal to `detect a Python app`__.
    :class: tip

    That's why you don't need to declare that you need a Python runtime.

    __ https://www.koyeb.com/docs/build-and-deploy/build-from-git/python#detection

Create a ``Procfile`` file with this content to configure the command for
running the server:

.. literalinclude:: ../../example/tutorial/step3/Procfile
    :language: text

Commit and push your changes:

.. code-block:: console

    $ git add .
    $ git commit -m "Deploy to Koyeb."
    [main 4a4b6e9] Deploy to Koyeb.
     3 files changed, 15 insertions(+), 2 deletions(-)
     create mode 100644 Procfile
     create mode 100644 requirements.txt
    $ git push
    ...
    To github.com:python-websockets/websockets-tutorial.git
    + 6bd6032...4a4b6e9 main -> main

Sign up or log in to Koyeb.

In the Koyeb control panel, create a web service with GitHub as the deployment
method. `Install and authorize Koyeb's GitHub app`__ if you haven't done that yet.

__ https://www.koyeb.com/docs/build-and-deploy/deploy-with-git#connect-your-github-account-to-koyeb

Follow the steps to create a new service:

1. Select the ``websockets-tutorial`` repository in the list of your repositories.
2. Confirm that the **Free** instance type is selected. Click **Next**.
3. Configure health checks: change the protocol from TCP to HTTP and set the
   path to ``/healthz``. Review other settings; defaults should be correct.
   Click **Deploy**.

Koyeb builds the app, deploys it, verifies that the health checks passes, and
makes the deployment active.

You can test the WebSocket server with the interactive client exactly like you
did in the first part of the tutorial. The Koyeb control panel provides the URL
of your app in the format: ``https://<app>-<user>-<id>.koyeb.app/``. Replace
``https`` with ``wss`` in the URL and connect the interactive client:

.. code-block:: console

    $ websockets wss://<app>-<user>-<id>.koyeb.app/
    Connected to wss://<app>-<user>-<id>.koyeb.app/.
    > {"type": "init"}
    < {"type": "init", "join": "54ICxFae_Ip7TJE2", "watch": "634w44TblL5Dbd9a"}

Press Ctrl-D to terminate the connection.

It works!

Prepare the web application
---------------------------

Before you deploy the web application, perhaps you're wondering how it will
locate the WebSocket server? Indeed, at this point, its address is hard-coded
in ``main.js``:

.. code-block:: javascript

  const websocket = new WebSocket("ws://localhost:8001/");

You can take this strategy one step further by checking the address of the
HTTP server and determining the address of the WebSocket server accordingly.

Add this function to ``main.js``; replace ``python-websockets`` by your GitHub
username and ``websockets-tutorial`` by the name of your app on Koyeb:

.. literalinclude:: ../../example/tutorial/step3/main.js
    :language: js
    :start-at: function getWebSocketServer
    :end-before: function initGame

Then, update the initialization to connect to this address instead:

.. code-block:: javascript

  const websocket = new WebSocket(getWebSocketServer());

Commit your changes:

.. code-block:: console

    $ git add .
    $ git commit -m "Configure WebSocket server address."
    [main 0903526] Configure WebSocket server address.
     1 file changed, 11 insertions(+), 1 deletion(-)
    $ git push
    ...
    To github.com:python-websockets/websockets-tutorial.git
    + 4a4b6e9...968eaaa main -> main

Deploy the web application
--------------------------

Go back to GitHub, open the Settings tab of the repository and select Pages in
the menu. Select the main branch as source and click Save. GitHub tells you
that your site is published.

Open https://<your-username>.github.io/websockets-tutorial/ and start a game!

Summary
-------

In this third part of the tutorial, you learned how to deploy a WebSocket
application with Koyeb.

You can start a Connect Four game, send the JOIN link to a friend, and play
over the Internet!

Congratulations for completing the tutorial. Enjoy building real-time web
applications with websockets!

Solution
--------

.. literalinclude:: ../../example/tutorial/step3/app.py
    :caption: app.py
    :language: python
    :linenos:

.. literalinclude:: ../../example/tutorial/step3/index.html
    :caption: index.html
    :language: html
    :linenos:

.. literalinclude:: ../../example/tutorial/step3/main.js
    :caption: main.js
    :language: js
    :linenos:

.. literalinclude:: ../../example/tutorial/step3/Procfile
    :caption: Procfile
    :language: text
    :linenos:

.. literalinclude:: ../../example/tutorial/step3/requirements.txt
    :caption: requirements.txt
    :language: text
    :linenos:
