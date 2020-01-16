#!/usr/bin/env python
import sys
import json
import logging
from argparse import ArgumentParser, RawDescriptionHelpFormatter, FileType, SUPPRESS

from lumapps.api.errors import ApiCallError
from lumapps.api.utils import (
    list_prune_filters,
    get_config_names,
    get_config,
    set_config,
)
from lumapps.api import ApiClient, TokenClient

LIST_CONFIGS = "***LIST_CONFIGS***"


def parse_args(*args, **kwargs):
    parser = ArgumentParser(formatter_class=RawDescriptionHelpFormatter, add_help=False)
    add_arg = parser.add_argument
    group1 = parser.add_mutually_exclusive_group()
    group2 = parser.add_mutually_exclusive_group()
    add_arg(
        "endpoint",
        nargs="*",
        metavar="ENDPOINT_AND_PARAMETERS",
        help="Parameters are set as arg_name=value",
    )
    add_arg("--help", "-h", action="store_true")
    add_arg("--debug", "-d", action="store_true")
    add_arg("--proxy", help="JSON file", metavar="FILE")
    add_arg("--no-verify", help="disable SSL verification", action="store_true")
    add_arg("--api", help="JSON file", metavar="FILE")
    group2.add_argument("--auth", help="JSON auth file", metavar="FILE")
    group2.add_argument("--token")
    group1.add_argument(
        "--user", metavar="EMAIL", help="use domain wide delegation for this user"
    )
    group1.add_argument("--email", help="use user/getToken to get token for this email")
    add_arg("--customer-id", help="may be required when using --email")
    add_arg("--body-file", help="JSON POST data body file", metavar="FILE")
    add_arg("-p", "--prune", action="store_true", help="reomove extraneous content")
    add_arg("--list-prune-filters", action="store_true")
    add_arg(
        "-c",
        "--config",
        nargs="?",
        default=None,
        const=LIST_CONFIGS,
        help="SAVE/READ/LIST configuration(s): if a value is provided: "
        "SAVE when --auth or --api is specified, READ otherwise; if "
        "no value is provided: list saved configs",
        metavar="CONF_NAME",
    )
    add_arg("body", nargs="?", type=FileType("r"), default=sys.stdin, help=SUPPRESS)
    return parser, parser.parse_args(*args, **kwargs)


def list_configs():
    conf_names = get_config_names()
    if not conf_names:
        print("There are no saved configs")
        return
    print("Saved configs:")
    for conf_name in conf_names:
        print("  " + conf_name)


def load_config(api_file, auth_file, user, conf_name):
    if conf_name:
        conf = get_config(conf_name) or {}
        if not conf and not auth_file:
            sys.exit('config "{}" not found'.format(conf_name))
    else:
        conf = {}
    if auth_file:
        with open(auth_file) as fh:
            auth_info = json.load(fh)
    else:
        auth_info = conf.get("auth", None)
    if api_file:
        with open(api_file) as fh:
            api_info = json.load(fh)
    else:
        api_info = conf.get("api", None)
    if not user:
        user = conf.get("user", None)
    return api_info, auth_info, user


def store_config(api_info, auth_info, conf_name, user=None):
    set_config(conf_name, {"api": api_info, "auth": auth_info, "user": user})


def cast_params(name_parts, params, api):
    truths = ("True", "true", "1", "Yes", "yes", "sure", "yeah")
    method = api.endpoints[name_parts]
    method_params = method.get("parameters", {})
    for param in params:
        if method_params.get(param, {}).get("type", "") == "boolean":
            params[param] = params[param] in truths


def setup_logger():
    level = logging.DEBUG
    logger = logging.getLogger()
    logger.setLevel(level)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s]: %(message)s")
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch.setFormatter(formatter)
    logger.addHandler(ch)


def main():
    arg_parser, args = parse_args()
    if args.list_prune_filters:
        list_prune_filters()
        return
    if args.debug:
        setup_logger()
    if not (args.auth or args.api or args.config or args.token):
        arg_parser.print_help()
        return
    if args.config == LIST_CONFIGS:
        list_configs()
        return
    if args.proxy:
        with open(args.proxy) as fh:
            proxy_info = json.load(fh)
    else:
        proxy_info = None
    api_info, auth_info, user = load_config(args.api, args.auth, args.user, args.config)
    if args.email:
        token_client = TokenClient(
            args.customer_id, auth_info, api_info, no_verify=args.no_verify
        )
        token_getter = token_client.get_token_getter(args.email)
    else:
        token_getter = None
    api = ApiClient(
        auth_info,
        api_info,
        user=user,
        token=args.token,
        token_getter=token_getter,
        prune=args.prune,
        proxy_info=proxy_info,
        no_verify=args.no_verify,
    )
    if args.config and (args.auth or args.api):
        store_config(api_info, auth_info, args.config, args.user)
    if not args.endpoint:
        arg_parser.print_help()
        sys.exit(
            "\nNo endpoint specified. Found these:\n"
            + api.get_method_descriptions(sorted(api.endpoints))
        )
    name_parts = tuple(p for p in args.endpoint if "=" not in p)
    if name_parts not in api.endpoints:
        sys.exit(api.get_matching_endpoints(name_parts))
    if args.help:
        print(api.get_help(name_parts, args.debug))
        return
    params = {p[0]: p[2] for p in (a.partition("=") for a in args.endpoint if "=" in a)}
    if args.body_file:
        with open(args.body_file) as fh:
            params["body"] = json.load(fh)
    elif "body" in params:
        params["body"] = json.loads(params["body"])
    # elif not sys.stdin.isatty() and args.body:
    #     s = args.body.read()
    #     print('will loads this: {}'.format(s))
    #     params['body'] = json.loads(s)
    cast_params(name_parts, params, api)
    try:
        response = api.get_call(*name_parts, **params)
    except ApiCallError as err:
        sys.exit(err)
    print(json.dumps(response, indent=4, sort_keys=True))


if __name__ == "__main__":
    main()
