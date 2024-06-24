import os
import re
import requests
import pandas as pd
from datetime import datetime, timedelta
from dateutil import parser
from dotenv import load_dotenv
from urllib.parse import quote
from chatterbot import ChatBot
from chatterbot.trainers import ChatterBotCorpusTrainer, ListTrainer
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

load_dotenv()

# Database setup
Base = declarative_base()
engine = create_engine('sqlite:///database.sqlite3', connect_args={'check_same_thread': False})
Session = sessionmaker(bind=engine)
session = Session()

class WeatherData(Base):
    __tablename__ = 'weather_data'
    id = Column(Integer, primary_key=True)
    city = Column(String, nullable=False)
    datetime = Column(DateTime, nullable=False)
    temperature = Column(Float, nullable=False)
    description = Column(String, nullable=False)

Base.metadata.create_all(engine)

# Initialize Chatterbot
chatbot = ChatBot(
    'WeatherBot',
    storage_adapter='chatterbot.storage.SQLStorageAdapter',
    database_uri='sqlite:///database.sqlite3'
)

# Create a new trainer for the chatbot
trainer = ChatterBotCorpusTrainer(chatbot)

# Train the chatbot based on the English corpus
trainer.train('chatterbot.corpus.english')

# Train the chatbot with custom weather conversations
trainer.train('./corpus/weather.yml')

# Train the chatbot with additional custom conversations
custom_conversations = [
    "What is your name?",
    "My name is Low budget WeatherBot.",
    "How are you?",
    "I'm doing great.",
    "What can you do?",
    "I can provide weather updates and answer general questions."
]

list_trainer = ListTrainer(chatbot)
list_trainer.train(custom_conversations)

def kel_to_cel(kelvin_temp):
    return round(kelvin_temp - 273.15, 2)

predefined_coordinates = {
    "Cumbria": {"lat": 54.4609, "lon": -3.0886},
    "Corfe Castle": {"lat": 50.6395, "lon": -2.0566},
    "The Cotswolds": {"lat": 51.8330, "lon": -1.8433},
    "Cambridge": {"lat": 52.2053, "lon": 0.1218},
    "Bristol": {"lat": 51.4545, "lon": -2.5879},
    "Oxford": {"lat": 51.7520, "lon": -1.2577},
    "Norwich": {"lat": 52.6309, "lon": 1.2974},
    "Stonehenge": {"lat": 51.1789, "lon": -1.8262},
    "Watergate Bay": {"lat": 50.4429, "lon": -5.0553},
    "Birmingham": {"lat": 52.4862, "lon": -1.8904}
}

def get_city_coordinates(city):
    city_lower = city.lower()
    for predefined_city, coords in predefined_coordinates.items():
        if city_lower == predefined_city.lower():
            return coords['lat'], coords['lon']
    
    api_key = os.getenv('OPENWEATHERMAP_API_KEY')
    encoded_city = quote(city)
    url = f'http://api.openweathermap.org/geo/1.0/direct?q={encoded_city}&limit=1&appid={api_key}'
    response = requests.get(url)
    data = response.json()
    
    print(f"Geocoding API response for {city}: {data}")  

    if not data:
        print(f"Error fetching coordinates for {city}: {data}")
        return None, None

    return data[0]['lat'], data[0]['lon']

def fetch_weather_data(city, date=None):
    api_key = os.getenv('OPENWEATHERMAP_API_KEY')
    lat, lon = get_city_coordinates(city)
    if lat is None or lon is None:
        return None
    
    # Using 5 day / 3 hour forecast endpoint
    # https://openweathermap.org/forecast5
    url = f'http://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={api_key}'
    
    response = requests.get(url)
    data = response.json()

    print(f"API response for {city}: {data}")  # Detailed logging in terminal

    if 'list' not in data:
        print(f"Error fetching weather data: {data}")  # Detailed logging in terminal
        return None

    forecast_list = []
    for entry in data['list']:
        forecast_list.append({
            'datetime': entry['dt_txt'],
            'temperature': kel_to_cel(entry['main']['temp']),
            'description': entry['weather'][0]['description']
        })

    # Save to database
    for entry in forecast_list:
        weather_entry = WeatherData(
            city=city,
            datetime=datetime.strptime(entry['datetime'], '%Y-%m-%d %H:%M:%S'),
            temperature=entry['temperature'],
            description=entry['description']
        )
        session.add(weather_entry)
    session.commit()

    # Convert to pandas DataFrame
    forecast_df = pd.DataFrame(forecast_list)
    return forecast_df

def get_weather_data(city, date=None):
    # Check if we have recent data in the database
    query = session.query(WeatherData).filter(WeatherData.city == city)
    if date:
        query = query.filter(
            WeatherData.datetime >= date,
            WeatherData.datetime < date + timedelta(days=1)
        )
    else:
        query = query.filter(
            WeatherData.datetime > datetime.utcnow() - timedelta(hours=1)
        )
    recent_data = query.all()

    if recent_data:
        last_entry = recent_data[-1]
        time_diff = datetime.utcnow() - last_entry.datetime
        print(f"Time difference since last entry for {city}: {time_diff}")
        if time_diff > timedelta(hours=3):
            print(f"Cached data for {city} is older than 3 hours. Fetching new data.")
            forecast_df = fetch_weather_data(city, date)
        else:
            print(f"Using cached data for {city}")
            forecast_list = [{
                'datetime': entry.datetime.strftime('%Y-%m-%d %H:%M:%S'),
                'temperature': entry.temperature,
                'description': entry.description
            } for entry in recent_data]
            forecast_df = pd.DataFrame(forecast_list)
    else:
        print(f"Fetching new data for {city}")
        forecast_df = fetch_weather_data(city, date)
        if forecast_df is None:
            return f"Could not fetch weather data for {city}. Please check the city name and try again."
    return forecast_df

def format_date(date_str):
    date = datetime.strptime(date_str, '%Y-%m-%d')
    now = datetime.now()
    if date.date() == now.date():
        return "Today"
    elif date.date() == (now + timedelta(days=1)).date():
        return "Tomorrow"
    else:
        return date.strftime('%a %d')

def summarize_forecast(forecast_df):
    forecast_df['date'] = forecast_df['datetime'].apply(lambda x: x.split(' ')[0])
    summary = forecast_df.groupby('date').agg(
        avg_temp=('temperature', 'mean'),
        descriptions=('description', lambda x: ', '.join(set(x)))
    ).reset_index()

    summary['date'] = summary['date'].apply(format_date)
    summary['avg_temp'] = summary['avg_temp'].round(2)
    
    return summary

def get_chatbot_response(message):
    print(f"Received message: {message}")
    # Use regular expressions to match different patterns
    # What is the weather (in/for/at) OXFORD yyyy/mm/dd or(today / tomorrow / yesterday)
    match = re.search(r'weather (in|for|at)\s+([\w\s]+)(?:\s+on\s+(\d{4}-\d{2}-\d{2})|\s+(today|tomorrow|yesterday))?', message.lower())
    if match:
        city = match.group(2).strip()
        date_str = match.group(3)
        relative_day = match.group(4)

        if date_str:
            date = parser.parse(date_str)
        elif relative_day:
            if relative_day == "today":
                date = datetime.now()
            elif relative_day == "tomorrow":
                date = datetime.now() + timedelta(days=1)
            elif relative_day == "yesterday":
                date = datetime.now() - timedelta(days=1)
        else:
            date = None

        print(f"Fetching weather data for city: {city} on date: {date}")
        weather_data = get_weather_data(city, date)
        if isinstance(weather_data, str):  # Check if the response is an error message
            return weather_data

        summary = summarize_forecast(weather_data)

        response = f"<strong>Weather forecast for {city}:</strong><br>"
        for _, row in summary.iterrows():
            response += f"<div>{row['date']}: {row['avg_temp']}°C, {row['descriptions'].split(', ')[0]}</div>"
        return response
    else:
        response = chatbot.get_response(message)
        return str(response)
