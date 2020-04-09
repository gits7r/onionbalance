.. _onionbalance_config:

onionbalance-config Tool
========================

Description
-----------

The ``onionbalance-config`` tool is the fastest way to generate the necessary
keys and config files to get your onion service up and running.

.. code-block:: console

    $ onionbalance-config

When called without any arguments, the config generator will run in an
interactive mode and prompt for user input.

The ``master`` directory should be stored on the management server while
the other ``instance`` directories should be transferred to the respective
backend servers.


Files
-----

master/config.yaml
  This is the configuration file that is used my the OnionBalance management
  server.

master/<ONION_ADDRESS>.key
  The private key which will become the public address and identity for your
  onion service. It is essential that you keep this key secure.

srv/<ONION_ADDRESS>/private_key
  Directory containing the private key for you backend onion service instance.
  This key is less critical as it can be rotated if lost or compromised.


See Also
--------

Full documentation for the **OnionBalance** software is available at
https://onionbalance.readthedocs.org/
