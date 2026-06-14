import tkinter as tk
import webbrowser
from PIL import Image, ImageTk
import os

def show_about_dialog(logo_path):
    root = tk.Tk()
    root.title("About itchcord")
    root.geometry("400x400")
    root.resizable(False, False)
    
    # Try to center window
    root.eval('tk::PlaceWindow . center')
    
    # Make it stay on top
    root.attributes('-topmost', True)

    try:
        # Load and resize logo
        img = Image.open(logo_path)
        img = img.resize((128, 128), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        
        logo_label = tk.Label(root, image=photo)
        logo_label.image = photo # keep reference
        logo_label.pack(pady=(20, 10))
    except Exception as e:
        print(f"Could not load logo: {e}")
        pass

    title_label = tk.Label(root, text="itchcord", font=("Helvetica", 20, "bold"))
    title_label.pack()

    desc_label = tk.Label(root, text="Discord Rich Presence for itch.io games", font=("Helvetica", 12))
    desc_label.pack(pady=(0, 20))
    
    dev_label = tk.Label(root, text="Developer: Abhishek Verma", font=("Helvetica", 10, "bold"))
    dev_label.pack()

    def open_link(url):
        webbrowser.open_new(url)

    links = [
        ("GitHub", "https://github.com/w3Abhishek/itchcord"),
        ("Telegram", "https://telegram.me/w3Abhishek"),
        ("X (Twitter)", "https://x.com/pyvrma")
    ]

    for text, url in links:
        link = tk.Label(root, text=text, fg="blue", cursor="hand2", font=("Helvetica", 10, "underline"))
        link.pack(pady=2)
        link.bind("<Button-1>", lambda e, u=url: open_link(u))

    close_btn = tk.Button(root, text="Close", command=root.destroy, width=15)
    close_btn.pack(side=tk.BOTTOM, pady=20)

    root.mainloop()
