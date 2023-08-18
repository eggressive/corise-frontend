import modal

def download_whisper():
  # Load the Whisper model
  import os
  import whisper
  print ("Download the Whisper model")

  # Perform download only once and save to Container storage
  whisper._download(whisper._MODELS["medium"], '/content/podcast/', False)


stub = modal.Stub("corise-podcast-project")
corise_image = modal.Image.debian_slim().pip_install("feedparser",
                                                     "https://github.com/openai/whisper/archive/9f70a352f9f8630ab3aa0d06af5cb9532bd8c21d.tar.gz",
                                                     "requests",
                                                     "ffmpeg",
                                                     "openai",
                                                     "tiktoken",
                                                     "wikipedia",
                                                     "ffmpeg-python").apt_install("ffmpeg").run_function(download_whisper)

@stub.function(image=corise_image, gpu="any", timeout=1200)
def get_transcribe_podcast(rss_url, local_path):
  print ("Starting Podcast Transcription Function")
  print ("Feed URL: ", rss_url)
  print ("Local Path:", local_path)

  # Read from the RSS Feed URL
  import feedparser
  intelligence_feed = feedparser.parse(rss_url)
  podcast_title = intelligence_feed['feed']['title']
  episode_title = intelligence_feed.entries[0]['title']
  episode_image = intelligence_feed['feed']['image'].href
  for item in intelligence_feed.entries[0].links:
    if (item['type'] == 'audio/mpeg'):
      episode_url = item.href
  episode_name = "podcast_episode.mp3"
  print ("RSS URL read and episode URL: ", episode_url)

  # Download the podcast episode by parsing the RSS feed
  from pathlib import Path
  p = Path(local_path)
  p.mkdir(exist_ok=True)

  print ("Downloading the podcast episode")
  import requests
  with requests.get(episode_url, stream=True) as r:
    r.raise_for_status()
    episode_path = p.joinpath(episode_name)
    with open(episode_path, 'wb') as f:
      for chunk in r.iter_content(chunk_size=8192):
        f.write(chunk)

  print ("Podcast Episode downloaded")

  # Load the Whisper model
  import os
  import whisper

  # Load model from saved location
  print ("Load the Whisper model")
  model = whisper.load_model('medium', device='cuda', download_root='/content/podcast/')

  # Perform the transcription
  print ("Starting podcast transcription")
  result = model.transcribe(local_path + episode_name)

  # Return the transcribed text
  print ("Podcast transcription completed, returning results...")
  output = {}
  output['podcast_title'] = podcast_title
  output['episode_title'] = episode_title
  output['episode_image'] = episode_image
  output['episode_transcript'] = result['text']
  return output

@stub.function(image=corise_image, secret=modal.Secret.from_name("my-openai-secret"))
def get_podcast_summary(podcast_transcript):
  import openai
  instructPrompt = """
    I am providing you with a transcription of a podcast.
    Write an entertaining summary of the podcast in the tone of Joe Rogan:
  """

  request = instructPrompt + "~~~"+ podcast_transcript + "~~~"
  chatOutput = openai.ChatCompletion.create(model="gpt-4",
                                            messages=[{"role": "system", "content": "You are an expert copywriter who publishes popular newsletters about podcasts. You just listened to this podcast that you want to summarize and share with your readers, to get them to listen to the podcast. "},
                                                      {"role": "user", "content": request}
                                                      ]
                                            )
  podcastSummary = chatOutput.choices[0].message.content



  return podcastSummary

@stub.function(image=corise_image, secret=modal.Secret.from_name("my-openai-secret"))
def get_podcast_guest(podcast_transcript):
  import openai
  import wikipedia
  import json

  request = podcast_transcript[:10000]
  completion = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": request}],
    functions=[
    {
        "name": "get_podcast_guest_information",
        "description": "Get information from Wikipedia on the podcast guest using their full name",
        "parameters": {
            "type": "object",
            "properties": {
                "guest_name": {
                    "type": "string",
                    "description": "Full name of the guest of the podcast",
                },
                "unit": {"type": "string"},
            },
            "required": ["guest_name"],
        },
    }
    ],
    function_call={"name": "get_podcast_guest_information"}
    )
  podcast_guest = ""
  response_message = completion["choices"][0]["message"]

  if response_message.get("function_call"):
    function_name = response_message["function_call"]["name"]
    function_args = json.loads(response_message["function_call"]["arguments"])
    podcast_guest=function_args.get("guest_name")

  print ("Podcast Guest is", podcast_guest)
  unknown = "Based off of the podcast, please create a Wikipedia style bio (hallucinate nothing) for the guest in this podcast named " + podcast_guest
  podcast_guest_info = ""
  try:
    input = wikipedia.page(podcast_guest, auto_suggest=True)
    podcast_guest_info = input.summary
  except wikipedia.DisambiguationError as e:

    # Get the first option from the disambiguation options
    first_option = e.options[0]
    input = wikipedia.page(first_option)
    podcast_guest_info = input.summary
  except wikipedia.PageError:

    chatOutputError = openai.ChatCompletion.create(model="gpt-4",
                                              messages=[{"role": "system", "content": "You are an expert copywriter who publishes popular newsletters about podcasts. You just listened to this podcast that you want to summarize and share with your readers, to get them to listen to the podcast. "},
                                                        {"role": "user", "content": unknown}
                                                        ]
                                              )

    podcast_guest_info = chatOutputError.choices[0].message.content


  podcastGuest = {}
  podcastGuest['name'] = podcast_guest

  podcastGuest['summary'] = podcast_guest_info

  return podcastGuest

@stub.function(image=corise_image, secret=modal.Secret.from_name("my-openai-secret"))
def get_podcast_highlights(podcast_transcript):
  import openai
  ### ADD YOUR LOGIC HERE TO RETURN THE HIGHLIGHTS OF THE PODCAST
  instructPrompt = """
    I am providing you with a transcription of a podcast. 
    Provide highlights of the podcast episode.

    * The host, [host name], interviewed [guest name], an expert on [guest's expertise].
    * [guest name] shared some fascinating insights on [topic of discussion].
    * Some of the key takeaways from the episode include:
      * [Key takeaway 1]
      * [Key takeaway 2]
      * [Key takeaway 3]
    """

  request = instructPrompt + "~~~" + podcast_transcript + "~~~" + "Highlights in bullet form: "
  chatOutput = openai.ChatCompletion.create(model="gpt-4",
                                            messages=[{"role": "system", "content": "You are an expert podcast reviewer and analyst, and you've just finished listening to a thrilling podcast episode."},
                                                      {"role": "user", "content": request}
                                                      ]
                                            )
  podcastHighlights = chatOutput.choices[0].message.content

  return podcastHighlights

@stub.function(image=corise_image, secret=modal.Secret.from_name("my-openai-secret"), timeout=1200)
def process_podcast(url, path):
  output = {}
  podcast_details = get_transcribe_podcast.call(url, path)
  podcast_summary = get_podcast_summary.call(podcast_details['episode_transcript'])
  podcast_guest = get_podcast_guest.call(podcast_details['episode_transcript'])
  podcast_highlights = get_podcast_highlights.call(podcast_details['episode_transcript'])
  podcast_dalle = get_podcast_dalle.call(podcast_details['episode_transcript'])
  output['podcast_details'] = podcast_details
  output['podcast_summary'] = podcast_summary
  output['podcast_guest'] = podcast_guest
  output['podcast_highlights'] = podcast_highlights
  output['podcast_dalle'] = podcast_dalle
  return output

@stub.local_entrypoint()
def test_method(url, path):
  output = {}
  podcast_details = get_transcribe_podcast.call(url, path)
  print ("Podcast Summary: ", get_podcast_summary.call(podcast_details['episode_transcript']))
  print ("Podcast Guest Information: ", get_podcast_guest.call(podcast_details['episode_transcript']))
  print ("Podcast Highlights: ", get_podcast_highlights.call(podcast_details['episode_transcript']))
  print ("Podcast DALLE PIC: ", get_podcast_dalle.call(podcast_details['episode_transcript']))