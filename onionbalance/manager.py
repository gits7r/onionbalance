# -*- coding: utf-8 -*-
"""
Load balance a hidden service across multiple (remote) Tor instances by
create a hidden service descriptor containing introduction points from
each instance.
"""
import sys
import argparse
import time
import os
import logging

# import Crypto.PublicKey
import stem
from stem.control import Controller, EventType
import yaml
import schedule

from onionbalance import log
from onionbalance import util
from onionbalance import config
from onionbalance import eventhandler

import onionbalance.service
import onionbalance.instance

logger = log.get_logger()


def parse_cmd_args():
    """
    Parses and returns command line arguments.
    """

    parser = argparse.ArgumentParser(
        description="%s distributes the requests for a Tor hidden services "
        "across multiple (remote) Tor instances." % sys.argv[0])

    parser.add_argument("-i", "--ip", type=str, default="127.0.0.1",
                        help="Tor controller IP address")

    parser.add_argument("-p", "--port", type=int, default=9051,
                        help="Tor controller port")

    parser.add_argument("-c", "--config", type=str,
                        default="config.yaml", help="Config file")

    parser.add_argument("-v", "--verbosity", type=str, default="info",
                        help="Minimum verbosity level for logging.  Available "
                             "in ascending order: debug, info, warning, "
                             "error, critical).  The default is info.")

    return parser.parse_args()


def parse_config_file(config_file):
    """
    Parse config file contain load balancing node configuration
    """
    config_path = os.path.abspath(config_file)
    if os.path.exists(config_path):
        with open(config_file, 'r') as handle:
            config_data = yaml.load(handle.read())
            logger.info("Loaded the config file '%s'.", config_path)
    else:
        logger.error("The specified config file '%s' does not exist.",
                     config_path)
        sys.exit(1)

    return config_data


def initialize_services(controller, services_config):
    """
    Load keys for services listed in the config
    """

    # Load the keys and config for each onion service
    for service in services_config:
        service_key = util.key_decrypt_prompt(service.get("key"))
        if not service_key:
            logger.error("Private key %s could not be loaded.",
                         service.get("key"))
            sys.exit(0)
        else:
            # Successfully imported the private key
            onion_address = util.calc_onion_address(service_key)
            logger.debug("Loaded private key for service %s.onion.",
                         onion_address)

        # Load all instances for the current onion service
        instance_config = service.get("instances", [])
        if not instance_config:
            logger.error("Could not load and instances for service "
                         "%s.onion.", onion_address)
            sys.exit(1)
        else:
            instances = []
            for instance in instance_config:
                instances.append(onionbalance.instance.Instance(
                    controller=controller,
                    onion_address=instance.get("address"),
                    authentication_cookie=instance.get("auth")
                ))

            logger.info("Loaded %d instances for service %s.onion.",
                        len(instances), onion_address)

        config.services.append(onionbalance.service.Service(
            controller=controller,
            service_key=service_key,
            instances=instances
        ))


def main():
    """
    Entry point when invoked over the command line.
    """
    args = parse_cmd_args()
    config_file_options = parse_config_file(args.config)

    # Update global configuration with options specified in the config file
    for setting in dir(config):
        if setting.isupper() and config_file_options.get(setting):
            setattr(config, setting, config_file_options.get(setting))

    logger.setLevel(logging.__dict__[args.verbosity.upper()])

    # Create a connection to the Tor control port
    try:
        controller = Controller.from_port(address=args.ip, port=args.port)
    except stem.SocketError as exc:
        logger.error("Unable to connect to Tor control port: %s", exc)
        sys.exit(1)
    else:
        logger.debug("Successfully connected to the Tor control port.")

    try:
        controller.authenticate()
    except stem.connection.AuthenticationFailure as exc:
        logger.error("Unable to authenticate to Tor control port: %s", exc)
        sys.exit(1)
    else:
        logger.debug("Successfully authenticated to the Tor control port.")

    # Disable no-member due to bug with "Instance of 'Enum' has no * member"
    # pylint: disable=no-member

    # Check that the Tor client supports the HSPOST control port command
    if not controller.get_version() >= stem.version.Requirement.HSPOST:
        logger.error("A Tor version >= %s is required. You may need to "
                     "compile Tor from source or install a package from "
                     "the experimental Tor repository.",
                     stem.version.Requirement.HSPOST)
        sys.exit(1)

    # Load the keys and config for each onion service
    initialize_services(controller, config_file_options.get('services'))

    # Finished parsing all the config file.

    handler = eventhandler.EventHandler()
    controller.add_event_listener(handler.new_desc,
                                  EventType.HS_DESC)
    controller.add_event_listener(handler.new_desc_content,
                                  EventType.HS_DESC_CONTENT)

    # Schedule descriptor fetch and upload events
    schedule.every(config.REFRESH_INTERVAL).seconds.do(
        onionbalance.instance.fetch_instance_descriptors, controller)
    schedule.every(config.PUBLISH_CHECK_INTERVAL).seconds.do(
        onionbalance.service.publish_all_descriptors)

    try:
        # Run initial fetch of HS instance descriptors
        schedule.run_all(delay_seconds=30)

        # Begin main loop to poll for HS descriptors
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Stopping the "
                    "management server.")
    return 0