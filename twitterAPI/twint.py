import os
import csv
import glob
import random

from time import sleep
from datetime import datetime

import twint

from tqdm import tqdm
from dotenv import load_dotenv

# from pymongo import errors as PyError
from pymongo import MongoClient

# Logging
from logger import logger as logger_perso

logger = logger_perso(name="twintAllAccount", stream_level="INFO", file_level="ERROR")

load_dotenv()


def download_test(userid, nbr_tweets):

    # Create an empty list of tweets to output
    tweets_output = []
    tempfilename = ".{}-temp".format(userid)

    # Create an empty file to store pagination id
    with open(tempfilename, "w", encoding="utf-8") as f:
        f.write(str(-1))

    tweet_data = []

    # twint may fail; give it up to 5 tries to return tweets
    c = twint.Config()
    c.Store_object = True
    c.Hide_output = True
    c.User_id = userid
    # c.Custom["tweet"] = ["id"]
    # c.Format = "{id}"
    # c.Custom["tweet"] = ["id"]
    # c.Resume = ".temp"

    c.Store_object_tweets_list = tweet_data

    twint.run.Search(c)

    tweets = [tweet.id for tweet in tweet_data]

    # for tweet in tweets:
    #     if tweet != "":
    #         tweets_output.append([tweet])

    os.remove(tempfilename)

    # Return list of tweets
    return tweets


def download_account_tweets(
    userid, nbr_tweets,
):
    """
    Download public Tweets from a given Twitter account and return as a list
    :param username: Twitter @ username to gather tweets.
    :param nbr_tweets: # of tweets to gather; None for all tweets.
    :return tweets: List of tweets from the Twitter account
    """

    # Create an empty list of tweets to output
    tweets_output = []
    tempfilename = ".{}-temp".format(userid)

    # Create an empty file to store pagination id
    with open(tempfilename, "w", encoding="utf-8") as f:
        f.write(str(-1))

    pbar = tqdm(range(nbr_tweets), desc="Oldest Tweet")
    for i in range((nbr_tweets // 20) - 1):
        sleep(5)
        tweet_data = []

        # twint may fail; give it up to 5 tries to return tweets
        for _ in range(0, 4):
            if len(tweet_data) == 0:
                c = twint.Config()
                c.Store_object = True
                c.Hide_output = True
                c.User_id = userid
                c.Limit = 40
                # c.Format = "{id}"
                c.Resume = tempfilename

                c.Store_object_tweets_list = tweet_data

                twint.run.Search(c)

                # If it fails, sleep before retry.
                if len(tweet_data) == 0:
                    pause_time = 5 * _
                    # logger.info("Failed {} times. Pause for {}s".format(_, pause_time))
                    sleep(pause_time)
            else:
                continue

        # If still no tweets after multiple tries, we're done
        if len(tweet_data) == 0:
            break

        if i > 0:
            tweet_data = tweet_data[20:]

            tweets = [tweet.id for tweet in tweet_data]

            for tweet in tweets:
                if tweet != "":
                    tweets_output.append(tweet)

        if i > 0:
            pbar.update(20)
        else:
            pbar.update(40)
    os.remove(tempfilename)

    # Return list of tweets
    return tweets_output


def connect_db():
    host = os.environ["DB_HOST"]
    port = int(os.environ["DB_MONGO_PORT"])
    database = os.environ["DB_MONGO_DATABASE"]
    user = os.environ["DB_MONGO_USER"]
    passw = os.environ["DB_MONGO_PASS"]
    client = MongoClient(host, port, username=user, password=passw)
    return client[database]


def write_to_csv(input_list, userid):
    csvname = "./data/twint/{}-twint-tweets.csv".format(userid)
    with open(csvname, "w") as csvfile:
        writer = csv.writer(csvfile, delimiter="\n")
        writer.writerow(input_list)


def get_ids_parsed():
    """ Return list of id already parsed"""
    folder = "../data/twint/"
    for f in glob.glob("{}*.csv".format(folder)):
        yield int(os.path.basename(f).split("-")[0]), f


def main():
    # Get the already parsed id
    list_already_parsed, filelist = [[i[0], i[1]] for i in get_ids_parsed()]
    print(list_already_parsed)

    raise
    mongodb = connect_db()
    collection_user = mongodb["users"]
    # collection_user_info = mongodb["users_info"]
    # collection_tweet = mongodb["tweets"]

    list_id_to_parse = [
        (i["screen_name"], i["id"], i["statuses_count"], i["protected"])
        for i in collection_user.find({})
    ]

    with open("list_id_to_parse", "w") as csvfile:
        writer = csv.writer(csvfile, delimiter="\n")
        writer.writerow(list_id_to_parse)
        # writer.writerow([i[1] for i in list_id_to_parse])

    for username, userid, statuses_count, protected in list_id_to_parse:
        if userid not in list_already_parsed:
            if protected is False:
                if statuses_count:
                    logger.info("User: {} - Protected: {}".format(username, protected))
                    logger.info("  Tweets: {}".format(statuses_count))
                    tweets = download_test(userid, statuses_count)
                    logger.info("  Collected: {}".format(len(tweets)))
                    # if len(tweets) > statuses_count / 2:
                    write_to_csv(tweets, userid)


if __name__ == "__main__":
    main()
