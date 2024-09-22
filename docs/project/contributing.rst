Contributing
============

Thanks for taking the time to contribute to websockets!

Code of Conduct
---------------

This project and everyone participating in it is governed by the `Code of
Conduct`_. By participating, you are expected to uphold this code. Please
report inappropriate behavior to aymeric DOT augustin AT fractalideas DOT com.

.. _Code of Conduct: https://github.com/python-websockets/websockets/blob/main/CODE_OF_CONDUCT.md

*(If I'm the person with the inappropriate behavior, please accept my
apologies. I know I can mess up. I can't expect you to tell me, but if you
choose to do so, I'll do my best to handle criticism constructively.
-- Aymeric)*

Contributing
------------

Bug reports, patches and suggestions are welcome!

Please open an issue_ or send a `pull request`_.

Feedback about the documentation is especially valuable, as the primary author
feels more confident about writing code than writing docs :-)

If you're wondering why things are done in a certain way, the :doc:`design
document <../topics/design>` provides lots of details about the internals of
websockets.

.. _issue: https://github.com/python-websockets/websockets/issues/new
.. _pull request: https://github.com/python-websockets/websockets/compare/

Packaging
---------

Some distributions package websockets so that it can be installed with the
system package manager rather than with pip, possibly in a virtualenv.

If you're packaging websockets for a distribution, you must use `releases
published on PyPI`_ as input. You may check `SLSA attestations on GitHub`_.

.. _releases published on PyPI: https://pypi.org/project/websockets/#files
.. _SLSA attestations on GitHub: https://github.com/python-websockets/websockets/attestations

You mustn't rely on the git repository as input. Specifically, you mustn't
attempt to run the main test suite. It isn't treated as a deliverable of the
project. It doesn't do what you think it does. It's designed for the needs of
developers, not packagers.

On a typical build farm for a distribution, tests that exercise timeouts will
fail randomly. Indeed, the test suite is optimized for running very fast, with a
tolerable level of flakiness, on a high-end laptop without noisy neighbors. This
isn't your context.
