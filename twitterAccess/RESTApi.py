#!/usr/bin/env python
# -*- coding: utf-8 -*-
# __author__ = "Olivier PHILIPPE"

"""
Attempt to write an  wrapper for the Twitter API.
It connect to the RestAPI and return a TwitterResponse object

source: https://stackoverflow.com/a/5558250
"""
import os
import time  # datetime.now().strftime('%Y-%m-%d %H:%M:%S')
import asyncio
import urllib.parse as urllib

from datetime import datetime

import requests

from requests import ConnectionError

from requests_oauthlib import OAuth1

# Logging
from logger import logger as logger_perso

logger = logger_perso(name="twitterRESTAPI", stream_level="INFO", file_level="ERROR")


# ### CONNECT ################################################


class TwitterResponse:
    """
    """

    def __init__(
        self, status, response, time_collected, api_call, max_id=None, since_id=None
    ):
        self.status = status
        self.response = response
        self.time_collected = time_collected
        self.api_call = api_call
        self.max_id = max_id
        self.since_id = since_id


class TwitterRESTAPI:
    """
    """

    def __init__(
        self,
        consumer_key: str,
        consumer_secret: str,
        access_token: str,
        access_token_secret: str,
        wait_on_pause: bool,
        dev_env: str = None,
    ):
        """
        wait_on_pause bool: to make the app pause on the error return or to return the error and continue
        dev_en str: the name of the dev environment to use Dev API endpoint. Default=None
        """
        self.wait_on_pause = wait_on_pause

        self.auth = self.create_auth(
            consumer_key, consumer_secret, access_token, access_token_secret
        )
        self.loop = asyncio.get_event_loop()
        self.dev_env = dev_env

    def async_loop(f):
        def decorated(self, *args, **kwargs):
            self.loop.run_until_complete(f(self, *args, **kwargs))

        return decorated

    def create_auth(
        self, consumer_key, consumer_secret, access_token, access_token_secret
    ):
        """
        """
        try:
            auth = OAuth1(
                consumer_key,
                client_secret=consumer_secret,
                resource_owner_key=access_token,
                resource_owner_secret=access_token_secret,
            )
            return auth
        except AttributeError:
            logger.critical("create_client: No Keys to connect, check the file")
            raise "No Keys to connect, check the file"

    def cursor_call(self, limit):
        """
        Used when a cursor methods is needed to parse results
        """
        if limit is None:
            while self.parameters["cursor"] != 0:
                result = self.create_URL()
                try:
                    self.parameters["cursor"] = result.response["next_cursor"]
                    # result.response = result.response['ids']
                    # Return only the id list without the cursors
                except TypeError:  # In case of 404, response is None
                    self.parameters["cursor"] = 0
                    # result.response = None
                yield result
        else:
            loop = 0
            while self.parameters["cursor"] != 0 and loop < limit:
                loop += 1
                result = self.create_URL()
                try:
                    self.parameters["cursor"] = result.response["next_cursor"]
                    # result.response = result.response['ids']
                    # Return only the id list without the cursors
                except TypeError:
                    self.parameters["cursor"] = 0
                    # result.response = None
                yield result

    def tweet_call(self):
        """
        Calling the next bunch of 200 tweets
        """
        check = True
        while check is True:
            result = self.create_URL()
            # Return a list of tweet, need to get the last tweet
            # To have the latest tweet. The -1 to avoid redundancies
            try:
                # Last return is an empty list because the last max_id match the last tweet
                result.max_id = int(result.response[-1]["id"]) - 1
                self.last_max_id = result.max_id
                self.parameters["max_id"] = result.max_id
                # self.parameters['since_id'] = result.since_id
                try:
                    result.since_id = self.since_id
                except AttributeError:  # Mean that it is the first since id
                    self.since_id = int(result.response[0]["id"])
                    result.since_id = self.since_id
            # Last return is an empty list because the last max_id match the last tweet
            # When try to collect response from a protected account
            # return the str() "protected" and break here
            # so just pass an go straight to the yield result
            except (IndexError, TypeError):
                try:
                    result.max_id = self.last_max_id
                except AttributeError:
                    result.max_id = None
                try:
                    result.since_id = self.since_id
                except AttributeError:
                    result.since_id = None
                check = False
            yield result

    # FIXME If it is a list that its passed like from user_look_up, it needs to be encored
    # as id=user_id. But when it is from the tweet_look_up, it is needs to be id=tweet_id,tweet_id
    # has to deal with both in a more elegant way than now
    def create_URL(self, url_encode=True):
        """
        Funct to create the URL with the parameters
        """
        BEGIN = "https://api.twitter.com/1.1/"
        # True as second element of urrlib is to encode a list
        self.params = urllib.urlencode(self.parameters, True)
        url = "{}{}{}".format(BEGIN, self.service, self.params)
        return self.create_call(url)

    def create_call(self, url):
        """
        Do the actual API call and return the response and status
        """
        try:
            resp = requests.get(url=url, auth=self.auth)
        except ValueError as e:
            logger.error("create_call: error {} - Pause for 5 sec".format(e))
            logger.error("create_call: resp from Twitter: {}".format(resp))
            time.sleep(5)
            logger.error("create_call: Ending Pause - Retry")
            return self.create_call(url)
        except requests.exceptions.ConnectionError as e:
            logger.error("create_call: error {} - Pause for 5 sec".format(e))
            time.sleep(5)
            logger.error("create_call: Ending Pause - Retry")
            return self.create_call(url)

        return self.check_response(resp)

    def check_response(self, resp):
        """
        Error codes: https://dev.twitter.com/docs/error-codes-responses
        """
        response = resp.json()
        status = resp.headers
        status_code = resp.status_code
        response_time = datetime.now()
        try:
            api_call = (
                self.api_type,
                int(status["x-rate-limit-remaining"]),
                int(status["x-rate-limit-limit"]),
                int(status["x-rate-limit-reset"]),
                status,
            )
        # Sometime get a wrong answer from twitter like expirat in 1981
        # Retry after a pause. Need to check later if the error is not
        # something I do wrong but seems wrong on their behalf
        except KeyError:
            logger.error(
                "check_response: KeyError: - resp: {} - status: {}".format(resp, status)
            )
            self.pause_API(status, status_code="KeyError", error_code=None)
            return self.create_URL()
        # In case of the connect is shutdown on the server level
        except ConnectionError:
            logger.error("check_response: Connect down to the server")
            self.pause_API(status, status_code="ConnectionError", error_code=None)
            return self.create_URL()

        if status_code == 200:
            if "error" in response:
                logger.error("check_response: Error in response: {}".format(response))
                # not existing resource
                if response["error"][0]["code"] == "34":
                    return TwitterResponse(34, None, response_time, api_call)
                # rate limit for the specific resource
                elif response["error"][0]["code"] == "88":
                    if self.wait_on_pause:
                        self.pause_API(status, status_code, error_code=88)
                        return self.create_URL()
                    else:
                        return TwitterResponse(88, None, response_time, api_call)
            else:
                return TwitterResponse(200, response, response_time, api_call)

        # Supposedly not right resource, seems to be raised when
        # Try to get informat from a secured account
        elif status_code == 401:
            return TwitterResponse(401, "protected", response_time, api_call)

        elif status_code == 429:
            if self.wait_on_pause:
                self.pause_API(status, status_code, error_code=429)
                return self.create_URL()
            else:
                return TwitterResponse(429, None, response_time, api_call)

        elif status_code == (500 or 502 or 503 or 504):
            if self.wait_on_pause:
                self.pause_API(status, status_code, error_code=None, response=response)
                return self.create_URL()

        elif status_code == 404:
            return TwitterResponse(404, None, response_time, api_call)
        elif status_code == 403:
            return TwitterResponse(403, "User suspended", response_time, api_call)
        else:
            return TwitterResponse(int(status_code), None, response_time, api_call)

    # FIXME Error with the self.time_reset
    # Check if it is a api limit more global
    # Should be done by the elt[-1] == 0
    # But sometime get a negative value
    def pause_API(self, status, status_code, error_code, response=None):
        """
        Pause the call and wait for the reset
        """

        if status_code == "KeyError":
            time_to_sleep = 30

        elif status_code == "ConnectionError":
            time_to_sleep = 30

        elif status_code == (500 or 502 or 503 or 504):
            logger.error("Twitter Internal error pause for 30 sec: {}".format(response))
            time_to_sleep = 30

        elif status_code == 429:
            reset = int(status["x-rate-limit-reset"])
            time_to_sleep = (reset - time.time()) + 2
            logger.info(
                "pause_API: Too much requests, pause for {} sec".format(time_to_sleep)
            )

        elif status_code == 200 & error_code == 88:  # Normal pause API
            reset = int(status["x-rate-limit-reset"])
            time_to_sleep = (reset - time.time()) + 2
            time_vis = datetime.fromtimestamp(reset)
            logger.info(
                "pause_API {} seconds - starting at {}".format(time_to_sleep, time_vis)
            )

        # FIXME Bug if the call is too soon, it pauses
        # Again and has the prevs value
        # Resulting in a negative value
        if time_to_sleep < 0:
            time_to_sleep = 10
        else:
            pass
        time.sleep(time_to_sleep)
        logger.info("pause_API finished - restarting")

    ###############################################################################
    def check_user_type(self, user):  # FIXME Buggy as screen_name can be int
        """
        Choose which method, screen_name or id_str
        """
        try:
            int(user)
            return {"user_id": user}
        except ValueError:
            return {"screen_name": user}

    def get_user(self, user):
        """
        Return a single user object - Limit of 180
        """
        self.parameters = self.check_user_type(user)
        self.api_type = "users"
        self.service = "users/show.json?"
        return self.create_URL()

    def rate_limit(self, service):
        """
        Possible types: statuses, friends, users, followers, trends, help
        """
        self.service = "applicat/rate_limit_status.json?"
        self.parameters = {"resources": service}
        return self.create_URL()

    def user_look_up(self, list_id):
        """
        Return a generator of 100 users objects
        """
        self.api_type = "users"
        self.service = "users/lookup.json?"
        if len(list_id) > 100:
            raise Exception(
                "look_up: Too big list: it is a {} and cannot be higher than 100".format(
                    len(list_id)
                )
            )
        list_params = [str(elt) for elt in list_id]
        self.parameters = {"user_id": list_params}
        list_user = self.create_URL()
        return TwitterResponse(
            list_user.status,
            list_user.response,
            list_user.time_collected,
            list_user.api_call,
        )

    def tweet_look_up(self, list_id):
        """
        Return a generator of 100 tweet objects
        """
        self.api_type = "statuses"
        self.service = "statuses/lookup.json?"
        if len(list_id) > 100:
            raise Exception(
                "tweet_look_up: Too big list: it is a {} and cannot be higher than 100".format(
                    len(list_id)
                )
            )
        list_params = [str(elt) for elt in list_id]
        self.parameters = {"id": ",".join(list_params)}
        list_user = self.create_URL()
        return TwitterResponse(
            list_user.status,
            list_user.response,
            list_user.time_collected,
            list_user.api_call,
        )

    def followers_list(self, user, limit=None):  # 'count':''
        """
        return a list of of followers ids with a limit of 5000
        """
        self.parameters = self.check_user_type(user)
        self.parameters["cursor"] = "-1"
        self.api_type = "followers"
        self.service = "followers/ids.json?"
        return self.cursor_call(limit)

    def friends_list(self, user, limit=None):  # 'count':''
        """
        return a list of of friends ids with a limit of 5000
        """
        self.parameters = self.check_user_type(user)
        self.parameters["cursor"] = "-1"
        self.api_type = "friends"
        self.service = "friends/ids.json?"
        return self.cursor_call(limit)

    def user_timeline(self, user, since_id=None, max_id=None):
        """
        Use the since_id: greater than and max_id: lesser than
        Use both id if they are passed so the applicat that use this API
        needs to deal with since_id and max_id before to be sure that all
        wanted tweets are collected
        """
        self.parameters = self.check_user_type(user)
        self.parameters["count"] = 200
        # If a max_id is present that means that the last check wasn't complete
        if max_id:
            self.parameters["max_id"] = int(max_id)
            self.last_max_id = int(max_id)  # FIXME Two variables for last_max_id
        if since_id:
            self.since_id = int(since_id)  # FIXME two variables for since_id
            self.parameters["since_id"] = int(since_id)
        self.api_type = "statuses"
        self.service = "statuses/user_timeline.json?"
        return self.tweet_call()

    def user_mentions(self, user, since_id=None, max_id=None):
        """
        Collect all the mention to the user
        Use the since_id: greater than and max_id: lesser than
        Use both id if they are passed so the applicat that use this API
        needs to deal with since_id and max_id before to be sure that all
        wanted tweets are collected
        """
        self.parameters = self.check_user_type(user)
        self.parameters["count"] = 200
        self.parameters["trim_user"] = False
        if max_id:
            self.parameters["max_id"] = int(max_id)
            self.last_max_id = int(max_id)  # FIXME Two variables for last_max_id
        if since_id:
            self.since_id = since_id  # FIXME two variables for since_id
            self.parameters["since_id"] = since_id
        self.api_type = "statuses"
        self.service = "statuses/mentions_timeline.json?"
        return self.tweet_call()

    def followers_id(self, user):
        """
        return a list of followers id object, only per 20 and a limit of 15/30
        """
        self.api_type = "followers"
        self.service = "followers/list.json?"
        self.parameters = {"screen_name": user, "cursor": "-1"}
        # FIXME in the cursor_call, have the result['ids'] which
        # didn't work with this call
        return self.cursor_call()

    def friends_id(self, user):
        """
        return a list of friends id object, only per 20 and a limit of 15/30
        """
        self.api_type = "friends"
        self.service = "friends/list.json?"
        self.parameters = {"user_id": user, "cursor": "-1", "skip_status": 1}
        return self.cursor_call()

    def search_tweets(self, search_terms: list(), since_id=None, max_id=None):
        """
        return a list of tweet object from the search_terms list
        """
        self.api_type = "search"
        self.service = "search/tweets.json"
        self.parameters = {"q": search_terms}
        if max_id:
            self.last_max_id = int(max_id)  # FIXME Two variables for last_max_id
            self.parameters["max_id"] = int(max_id)
        if since_id:
            self.since_id = since_id  # FIXME two variables for since_id
            self.parameters["since_id"] = since_id
        return self.cursor_call()

    def search_30_dev(self):

        raise NotImplementedError
        # https://api.twitter.com/1.1/tweets/search/30day/my_env_name.json


def main():
    """
    """
    from dotenv import load_dotenv

    # def get_keys(file_path=None):
    #     """
    #     Get the key from a file
    #     """
    #     twitter_keys = dict()
    #     if file_path is None:
    #         file_path = "twitterKeys.txt"
    #     try:
    #         with open(file_path, "r") as f:
    #             for line in f:
    #                 key, val = line.split(":")
    #                 twitter_keys[key] = val[:-1]
    #         return twitter_keys
    #     except OSError:
    #         raise OSError
    #
    # twitter_file = "./twitterKeys.txt"
    # twitter_keys = get_keys(twitter_file)
    #
    # consumer_key = twitter_keys["CONSUMER_KEY"]
    # consumer_secret = twitter_keys["CONSUMER_SECRET"]
    # access_token = twitter_keys["ACCESS_TOKEN"]
    # access_token_secret = twitter_keys["ACCESS_TOKEN_SECRET"]

    # ### LOAD ENV ################################################
    load_dotenv()
    consumer_key = os.environ["TWITTER_CONSUMER_KEY"]
    consumer_secret = os.environ["TWITTER_CONSUMER_SECRET"]
    access_token = os.environ["TWITTER_ACCESS_TOKEN"]
    access_token_secret = os.environ["TWITTER_ACCESS_TOKEN_SECRET"]

    test_api = TwitterRESTAPI(
        consumer_key,
        consumer_secret,
        access_token,
        access_token_secret,
        wait_on_pause=False,
    )
    while True:
        tweet_results = test_api.tweet("Oli_Ph")
        for tweet in tweet_results:
            print(tweet.status)
            print(tweet.response)
        followers_results = test_api.followers_list("Oli_Ph")
        for follower in followers_results:
            print(follower.status)
            print(follower.response)
    # for result in tweet_results:
    #     try:
    #         logger.info(
    #             "Status: {} - max_id {} - Since_id {} - len resp: {} - type resp: {}".format(
    #                 result.status,
    #                 result.max_id,
    #                 result.since_id,
    #                 len(result.response),
    #                 type(result.response),
    #             )
    #         )
    #     except TypeError:
    #         logger.info(
    #             "Status: {} - max_id: {} - since_id: {} - response:{}".format(
    #                 result.status, result.max_id, result.since_id, result.response,
    #             )
    #         )
    # result = test_api.get_user(60708088)
    # while True:
    #     for list_ in slice_list(lvl1, 100):
    #         # print(list_)
    #         result = test_api.tweet(list_)
    #         print(result.status)
    #         print(result.response)
    #         # for user in result.response:
    #             # print(user['id_str'])
    #             # print(result.status, result.response)


if __name__ == "__main__":
    """ """
    main()
