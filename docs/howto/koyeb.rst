Deploy to Koyeb
================

This guide describes how to deploy a websockets server to [Koyeb](https://www.koyeb.com).

**The free plan of Koyeb is sufficient for trying this guide. Koyeb natively supports long-running WebSockets connections.** 

We’re going to deploy a very simple app. The process would be identical to a more realistic app.

## **Create repository**

You can deploy WebSockets from a git repository. In this guide, we will showcase how to deploy from a GitHub repository. Let’s initialize one:

```
mkdir websockets-echo
cd websockets-echo
git init -b main
*Initialized empty Git repository in websockets-echo/.git/*

git commit --allow-empty -m "Initial commit."
*[main (root-commit) 816c3b1] Initial commit.*
```

Koyeb requires the git repository to be hosted at GitHub. Sign up or log in to GitHub. Create a new repository named `websockets-echo`. 

Push the existing repository from the command line.

```
git remote add origin git@github.com:<YOUR_GITHUB_USERNAME>/<YOUR_GITHUB_REPOSITORY>.git
git push -u origin main
```

After pushing, refresh your repository’s homepage on GitHub. You should see an empty repository with an empty initial commit.

## **Create application**

Here’s the implementation of the app, an echo server. Save it in a file called `app.py`:

```
#!/usr/bin/env python

import asyncio
import signal
import os

import websockets

async def echo(websocket):
    async for message in websocket:
				print(message) 
        await websocket.send(message)

async def main():
    # Set the stop condition when receiving SIGTERM.
    loop = asyncio.get_running_loop()
    stop = loop.create_future()
    loop.add_signal_handler(signal.SIGTERM, stop.set_result, None)

    async with websockets.serve(
        echo,
        host="",
        port=int(os.environ["PORT"]),
    ):
        await stop

if __name__ == "__main__":
    asyncio.run(main())
```

Create a `requirements.txt` file containing this line to declare a dependency on websockets:

```jsx
websockets
```

Confirm that you created the correct files and commit them to git:

```
ls
*app.py           requirements.txt*

git add .
git commit -m "Initial implementation."
*[main f26bf7f] Initial implementation.2 files changed, 37 insertions(+)create mode 100644 app.pycreate mode 100644 requirements.txt*
```

Push the changes to GitHub:

```jsx
git push
```

The app is ready. Let’s deploy it!

## **Deploy application**

Sign up or log in to [Koyeb](https://app.koyeb.com/). Then hit the **Create App** button.

1. Select GitHub as the deployment method and connect the git repository that you just created. The branch is automatically detected.
2. Under **Build and deployment settings**, specify the **Run command** to `python app.py`.
3. Finally, give your application a name, such as `websockets-echo` and click **Deploy**.

Once the deployment is complete and all necessary health checks have passed, you can access your public URL. `websockets-echo-<YOUR-ORG-NAME>.koyeb.app/`.

## **Validate deployment**

Let’s confirm that your application is running as expected.

Since it’s a WebSocket server, you need a WebSocket client, such as the interactive client that comes with websockets.

If you’re currently building a websockets server, perhaps you’re already in a virtualenv where websockets is installed. If not, you can install it in a new virtualenv as follows:

```
python -m venv websockets-client
. websockets-client/bin/activate
pip install websockets
```

Connect the interactive client — you must replace `websockets-echo` with the name of your Koyeb app in this command:

```
python -m websockets wss://websockets-echo-<YOUR-ORG-NAME>.koyeb.app/
*Connected to wss://websockets-echo-*<YOUR-ORG-NAME>*.koyeb.app/.>*
```

Great! Your app is running!

Once you’re connected, you can send any message and the server will echo it, or press Ctrl-D to terminate the connection:

```
*> Hello!
< Hello!
Connection closed: 1000 (OK).*
```

You can also confirm that your application shuts down gracefully when you deploy a new version. 

Connect an interactive client again — remember to replace `websockets-echo` with your app:

```
$ python -m websockets wss://websockets-echo-<YOUR-ORG-NAME>.koyeb.app/
*Connected to wss://websockets-echo-*<YOUR-ORG-NAME>*.koyeb.app/.>*
```

When the deployment completes, the connection is closed with code 1001 (going away).

```
$ python -m websockets wss://websockets-echo-<YOUR-ORG-NAME>.koyeb.app/
*Connected to wss://websockets-echo-*<YOUR-ORG-NAME>*.koyeb.app/.Connection closed: 1001 (going away).*
```
