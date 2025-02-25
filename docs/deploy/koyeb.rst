Deploy to Koyeb
================

This guide describes how to deploy a websockets server to Koyeb_.

.. _Koyeb: https://www.koyeb.com

.. admonition:: The free tier of Koyeb is sufficient for trying this guide.
    :class: tip

    The `free tier`__ include one web service, which this guide uses.

    __ https://www.koyeb.com/pricing

We’re going to deploy a very simple app. The process would be identical to a
more realistic app.

Create repository
-----------------

Koyeb supports multiple deployment methods. Its quick start guides recommend
git-driven deployment as the first option. Let's initialize a git repository:

.. code-block:: console

    $ mkdir websockets-echo
    $ cd websockets-echo
    $ git init -b main
    Initialized empty Git repository in websockets-echo/.git/
    $ git commit --allow-empty -m "Initial commit."
    [main (root-commit) 740f699] Initial commit.

Render requires the git repository to be hosted at GitHub.

Sign up or log in to GitHub. Create a new repository named ``websockets-echo``.
Don't enable any of the initialization options offered by GitHub. Then, follow
instructions for pushing an existing repository from the command line.

After pushing, refresh your repository's homepage on GitHub. You should see an
empty repository with an empty initial commit.

Create application
------------------

Here’s the implementation of the app, an echo server. Save it in a file
called ``app.py``:

.. literalinclude:: ../../example/deployment/koyeb/app.py
    :language: python

This app implements typical requirements for running on a Platform as a Service:

* it listens on the port provided in the ``$PORT`` environment variable;
* it provides a health check at ``/healthz``;
* it closes connections and exits cleanly when it receives a ``SIGTERM`` signal;
  while not documented, this is how Koyeb terminates apps.

Create a ``requirements.txt`` file containing this line to declare a dependency
on websockets:

.. literalinclude:: ../../example/deployment/koyeb/requirements.txt
    :language: text

Create a ``Procfile`` to tell Koyeb how to run the app.

.. literalinclude:: ../../example/deployment/koyeb/Procfile

Confirm that you created the correct files and commit them to git:

.. code-block:: console

    $ ls
    Procfile         app.py           requirements.txt
    $ git add .
    $ git commit -m "Initial implementation."
    [main f634b8b] Initial implementation.
     3 files changed, 39 insertions(+)
     create mode 100644 Procfile
     create mode 100644 app.py
     create mode 100644 requirements.txt

The app is ready. Let's deploy it!

Deploy application
------------------

Sign up or log in to Koyeb.

In the Koyeb control panel, create a web service with GitHub as the deployment
method. Install and authorize Koyeb's GitHub app if you haven't done that yet.

Follow the steps to create a new service:

1. Select the ``websockets-echo`` repository in the list of your repositories.
2. Confirm that the **Free** instance type is selected. Click **Next**.
3. Configure health checks: change the protocol from TCP to HTTP and set the
   path to ``/healthz``. Review other settings; defaults should be correct.
   Click **Deploy**.

Koyeb builds the app, deploys it, verifies that the health checks passes, and
makes the deployment active.

Validate deployment
-------------------

Let's confirm that your application is running as expected.

Since it's a WebSocket server, you need a WebSocket client, such as the
interactive client that comes with websockets.

If you're currently building a websockets server, perhaps you're already in a
virtualenv where websockets is installed. If not, you can install it in a new
virtualenv as follows:

.. code-block:: console

    $ python -m venv websockets-client
    $ . websockets-client/bin/activate
    $ pip install websockets

Look for the URL of your app in the Koyeb control panel. It looks like
``https://<app>-<user>-<id>.koyeb.app/``. Connect the
interactive client — you must replace ``https`` with ``wss``  in the URL:

.. code-block:: console

    $ websockets wss://<app>-<user>-<id>.koyeb.app/
    Connected to wss://<app>-<user>-<id>.koyeb.app/.
    >

Great! Your app is running!

Once you're connected, you can send any message and the server will echo it,
or press Ctrl-D to terminate the connection:

.. code-block:: console

    > Hello!
    < Hello!
    Connection closed: 1000 (OK).

You can also confirm that your application shuts down gracefully.

Connect an interactive client again:

.. code-block:: console

    $ websockets wss://<app>-<user>-<id>.koyeb.app/
    Connected to wss://<app>-<user>-<id>.koyeb.app/.
    >

In the Koyeb control panel, go to the **Settings** tab, click **Pause**, and
confirm.

Eventually, the connection gets closed with code 1001 (going away).

.. code-block:: console

    $ websockets wss://<app>-<user>-<id>.koyeb.app/
    Connected to wss://<app>-<user>-<id>.koyeb.app/.
    Connection closed: 1001 (going away).

If graceful shutdown wasn't working, the server wouldn't perform a closing
handshake and the connection would be closed with code 1006 (abnormal closure).
