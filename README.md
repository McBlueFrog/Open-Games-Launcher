# Open-Games-Launcher
A general open-source video game launcher be it your own or any other game

A clean, modern, open-source game launcher built in **Python + CustomTkinter**.  
It’s designed to be simple, customizable, and friendly for small indie projects, modded titles.


## ✨ Features

- 🧩 **Game List** — left-side menu with game icons and titles  
- ➕ **Add Game Quickly** — press the “+” to add an executable and it auto-creates JSON metadata  
- 🛠 **Edit Game Info** — open the JSON directly with one click  
- 📰 **News Feed** — pulls live text updates (Markdown or plain text) from a URL for each game  
- 🖼️ **Per-Game Cover** — top banner image refreshes when selecting a game  
- ⚙️ **Play / Update Buttons** — launch the game or download its latest update archive  
- 📦 **Auto-Extract ZIPs** — update packages are downloaded and unpacked automatically  
- 🌐 **Itch.io / MEGA Ready** — supports direct download links for both hosts  
- 🧠 **Open Source + Beginner Friendly** — easy to understand and edit

## Setup

 - Install python 3.10+
 - ```pip install -r requirements.txt```
 - ```python launcher.py```
 - That's it!

## How to use

There are two ways to add games,
### Manual method
By editing the ```games.json``` you can add your own games, icons, news feeds etc.
### Semi Automatic method
When starting the launcher you see a quick add button on the left panel it'll automatically helps you to select the path for the game and then you can edit the json
### Automatic method **Coming Soon**


## Example JSON

```
{
  "id": "mygame",
  "name": "My Game",
  "game_path": "C:/Games/MyGame/MyGame.exe",
  "work_dir": "C:/Games/MyGame",
  "icon": "assets/mygame_icon.png",
  "cover": "assets/mygame_cover.jpg",
  "news_url": "https://example.com/news.txt",
  "update": {
    "url": "https://yourname.itch.io/mygame/file/123456?dl=1",
    "dest": "C:/Games/MyGame/update.zip",
    "extract_to": "C:/Games/MyGame"
  }
}
```