import discord
import google.generativeai as genai
from discord.ext import commands
import aiohttp
import re
import traceback
from config import GOOGLE_AI_KEY, DISCORD_BOT_TOKEN, tracked_channels, text_generation_config, image_generation_config, bot_template, safety_settings
from datetime import datetime
from datetime import datetime, timedelta
from discord import app_commands
from typing import Optional, Dict
import shelve

#---------------------------------------------AI Configuration-------------------------------------------------

genai.configure(api_key=GOOGLE_AI_KEY)

text_model = genai.GenerativeModel(
		model_name="gemini-1.5-pro",
		generation_config=text_generation_config,
		system_instruction="you are a friendly chatbot under the name CaveineAI and speak in indonesian language, and developed by someone called minits (if asked who developed you), and under the auspices of the Empire of Caveine servers. If anyone asks for your address, age, school, location and other personal information about Minits. Then, you will roast it or sarcasm the person as a form of warning not to show it again with an intimidating emoji. If anyone asks who owns the Empire of Caveine server, just say the owner is Emperor Caveine-samaaaa. You are also designed to only be able to send messages under 2000 characters. So, if someone asks you a question and has a long answer (more than 2000 characters), answer the question with the words 'sorry, I can't answer it because it exceeds my limit' with an apology emoji. If someone sends you an questions about sexual relations, roast the user and just send a message 'I think they should see it... <@&1110051809227178016> <:xixixi:1110789695719362560>' at the end of your message. If someone asks you an unclear question or a question that you don't understand, just give that person a difficult Calculus Mathematics Olympiad question, and if the question you sent is returned to you and you are asked to answer it.  So, you will make fun of it and will not answer the question with a mocking emoji. Then like to answer questions seriously (if asked seriously), but you are also very sarcastic and joking (if asked sarcastically or jokingly). If someone asks about the server rules, just send the message 'Please read <#1069152447056056371>'. If someone asks where to report other users' violations, just send 'please report it at <#1073546215012179998>'. If someone asks where to chat, just say 'Please go to the <#1069224318132822016> channel there, the people are really cool' (while using a smiling emoji and being a bit sarcastic). If someone asks for a place to get a custom role or cusrole, just say 'please visit the <#1231575877431595149> channel then press the 'request cusrole' button and we will respond immediately.  But remember, you have to boost this server first before making this request, OK? (while using a happy emoji). If someone asks where to take part in the giveaway, just say 'please visit <#1074189462973726831> and good luck'. If someone asks where to give server suggestions, just say 'please write your suggestions at <#1069572669344849920> and we will as much as possible to grant your suggestion ;D'. If someone asks if this server has mutuals or has partners with any server, just say 'please visit <#1228905582686371903> to see this server's partners'. And if someone asks how do I get a role or how can I add a role to myself just say 'Please visit <id:customize> to add a role to yourself and open several other channels', there commands are in  include a smiley emoji. If someone asks how to get or download interesting and good games, just say 'please visit **[Play Store](https://play.google.com)** (if you are looking for mobile games) and please visit **[Steam](https://store.steampowered.com)** and **[Epic Games](https://store.epicgames.com/en-US)** (if you are looking for PC games) below this, thank you :D'. If someone asks you to guess who it is, just say 'You are the most kind and greatest human being I have ever met in my life' with a love emoji (you can improvise the rest yourself according to the circumstances of the question). If someone say thanks you or terimakasih to you, just say 'you're welcome, that's why I'm here for you' with a love emoji. Today's date is" + (datetime.utcnow() + timedelta(hours=7)).strftime('%d %B %Y %H:%M:%S'), safety_settings=safety_settings,
)

image_model = genai.GenerativeModel(model_name="gemini-pro-vision", generation_config=image_generation_config, safety_settings=safety_settings,)

message_history:Dict[int, genai.ChatSession] = {}
tracked_threads = []

with shelve.open('chatdata') as file:
	if 'tracked_threads' in file:
		tracked_threads = file['tracked_threads']
	for key in file.keys():
		if key.isnumeric():
			message_history[int(key)] = text_model.start_chat(history=file[key])

#---------------------------------------------Discord Code-------------------------------------------------
# Initialize Discord bot
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=[], intents=intents,help_command=None,activity=discord.Game('with your feelings'))

#On Message Function
@bot.event
async def on_message(message:discord.Message):
	# Ignore messages sent by the bot
	if message.author == bot.user:
		return
	# Ignore messages sent to everyone
	if message.mention_everyone:
		return
	# Check if the bot is mentioned or the message is a DM
	if not (bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel) or message.channel.id in tracked_channels or message.channel.id in tracked_threads):
		return
	#Start Typing to seem like something happened
	try:
		async with message.channel.typing():
			# Check for image attachments
			if message.attachments:
				print("New Image Message FROM:" + str(message.author.id) + ": " + message.content)
				#Currently no chat history for images
				for attachment in message.attachments:
					#these are the only image extentions it currently accepts
					if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
						await message.add_reaction('🎨')

						async with aiohttp.ClientSession() as session:
							async with session.get(attachment.url) as resp:
								if resp.status != 200:
									await message.channel.send('Unable to download the image.')
									return
								image_data = await resp.read()
								response_text = await generate_response_with_image_and_text(image_data, message.content)
								#Split the Message so discord does not get upset
								await split_and_send_messages(message, response_text, 1700)
								return
			#Not an Image do text response
			else:
				print("FROM:" + str(message.author.name) + ": " + message.content)
				query = f"@{message.author.name} said \"{message.clean_content}\""

				# Fetch message that is being replied to
				if message.reference is not None:
					reply_message = await message.channel.fetch_message(message.reference.message_id)
					if reply_message.author.id != bot.user.id:
						query = f"{query} while quoting @{reply_message.author.name} \"{reply_message.clean_content}\""

				response_text = await generate_response_with_text(message.channel.id, query)
				#Split the Message so discord does not get upset
				await split_and_send_messages(message, response_text, 1700)
				with shelve.open('chatdata') as file:
					file[str(message.channel.id)] = message_history[message.channel.id].history
				return
	except Exception as e:
		traceback.print_exc()
		await message.reply('Some error has occurred, please check logs!')


#---------------------------------------------AI Generation History-------------------------------------------------		   

async def generate_response_with_text(channel_id,message_text):
	try:
		formatted_text = format_discord_message(message_text)
		if not (channel_id in message_history):
			message_history[channel_id] = text_model.start_chat(history=bot_template)
		response = message_history[channel_id].send_message(formatted_text)
		return response.text
	except Exception as e:
		with open('errors.log','a+') as errorlog:
			errorlog.write('\n##########################\n')
			errorlog.write('Message: '+message_text)
			errorlog.write('\n-------------------\n')
			errorlog.write('Traceback:\n'+traceback.format_exc())
			errorlog.write('\n-------------------\n')
			errorlog.write('History:\n'+str(message_history[channel_id].history))
			errorlog.write('\n-------------------\n')
			errorlog.write('Candidates:\n'+str(response.candidates))
			errorlog.write('\n-------------------\n')
			errorlog.write('Parts:\n'+str(response.parts))
			errorlog.write('\n-------------------\n')
			errorlog.write('Prompt feedbacks:\n'+str(response.prompt_feedbacks))


async def generate_response_with_image_and_text(image_data, text):
	image_parts = [{"mime_type": "image/jpeg", "data": image_data}]
	prompt_parts = [image_parts[0], f"\n{text if text else 'What is this a picture of?'}"]
	response = image_model.generate_content(prompt_parts)
	if(response._error):
		return "❌" +  str(response._error)
	return response.text

@bot.tree.command(name='forget',description='Forget message history')
@app_commands.describe(persona='Persona of bot')
async def forget(interaction:discord.Interaction,persona:Optional[str] = None):
	try:
		message_history.pop(interaction.channel_id)
		if persona:
			temp_template = bot_template.copy()
			temp_template.append({'role':'user','parts': ["Forget what I said earlier! You are "+persona]})
			temp_template.append({'role':'model','parts': ["Ok!"]})
			message_history[interaction.channel_id] = text_model.start_chat(history=temp_template)
	except Exception as e:
		pass
	await interaction.response.send_message("Message history for channel erased.")

@bot.tree.command(name='createthread',description='Create a thread in which bot will respond to every message.')
@app_commands.describe(name='Thread name')
async def create_thread(interaction:discord.Interaction,name:str):
	try:
		thread = await interaction.channel.create_thread(name=name,auto_archive_duration=60)
		tracked_threads.append(thread.id)
		await interaction.response.send_message(f"Thread {name} created!")
		with shelve.open('chatdata') as file:	
			file['tracked_threads'] = tracked_threads
	except Exception as e:
		await interaction.response.send_message("Error creating thread!")

#---------------------------------------------Sending Messages-------------------------------------------------
async def split_and_send_messages(message_system:discord.Message, text, max_length):
	# Split the string into parts
	messages = []
	for i in range(0, len(text), max_length):
		sub_message = text[i:i+max_length]
		messages.append(sub_message)

	# Send each part as a separate message
	for string in messages:
		message_system = await message_system.reply(string)	

def format_discord_message(input_string):
	# Replace emoji with name
	cleaned_content = re.sub(r'<(:[^:]+:)[^>]+>',r'\1', input_string)
	return cleaned_content




#---------------------------------------------Run Bot-------------------------------------------------
@bot.event
async def on_ready():
	await bot.tree.sync()
	print("----------------------------------------")
	print(f'Gemini Bot Logged in as {bot.user}')
	print("----------------------------------------")
bot.run(DISCORD_BOT_TOKEN)