import streamlit as st
import chess
import chess.pgn
from io import StringIO, BytesIO
import asyncio
import time
import math
import os
import concurrent.futures
import mimetypes
import hashlib
import json
import base64

# Initialize session state
if 'user' not in st.session_state:
    st.session_state.user = None
if 'encoded_files' not in st.session_state:
    st.session_state.encoded_files = []
if 'decoded_files' not in st.session_state:
    st.session_state.decoded_files = []
if 'move_count' not in st.session_state:
    st.session_state.move_count = 0
if 'game_count' not in st.session_state:
    st.session_state.game_count = 0

# User authentication functions
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def load_users():
    if os.path.exists('users.json'):
        with open('users.json', 'r') as f:
            return json.load(f)
    return {}

def save_users(users):
    with open('users.json', 'w') as f:
        json.dump(users, f)

def load_user_data(username):
    if os.path.exists(f'{username}_data.json'):
        with open(f'{username}_data.json', 'r') as f:
            return json.load(f)
    return {'encoded_files': [], 'decoded_files': []}

def save_user_data(username, data):
    with open(f'{username}_data.json', 'w') as f:
        json.dump(data, f)

# Steganography functions
def to_binary_string(num: int, bits: int):
    return format(num, f'0{bits}b')

def get_pgn_games(pgn_string: str):
    games = []
    pgn_stream = StringIO(pgn_string)
    while True:
        game = chess.pgn.read_game(pgn_stream)
        if game is None:
            break
        games.append(game)
    return games

async def encode_chunk(chunk, start_index):
    chess_board = chess.Board()
    moves = []
    chunk_bit_index = 0
    chunk_bits = ''.join([format(byte, '08b') for byte in chunk])

    while chunk_bit_index < len(chunk_bits):
        legal_moves = list(chess_board.legal_moves)
        if not legal_moves:
            break
        max_binary_length = min(int(math.log2(len(legal_moves))), len(chunk_bits) - chunk_bit_index)
        
        next_chunk = chunk_bits[chunk_bit_index:chunk_bit_index + max_binary_length]
        if not next_chunk:
            break
        move_index = int(next_chunk, 2)
        move = legal_moves[min(move_index, len(legal_moves) - 1)]
        
        chess_board.push(move)
        moves.append(move)
        chunk_bit_index += max_binary_length

        st.session_state.move_count += 1

        if chess_board.is_game_over():
            st.session_state.game_count += 1
            break

    game = chess.pgn.Game()
    game.add_line(moves)
    return game

async def encode(file_bytes: bytes, num_bots: int):
    start_time = time.time()

    chunk_size = max(1, len(file_bytes) // num_bots)
    chunks = [file_bytes[i:i+chunk_size] for i in range(0, len(file_bytes), chunk_size)]

    tasks = [encode_chunk(chunk, i * chunk_size) for i, chunk in enumerate(chunks)]
    games = await asyncio.gather(*tasks)

    end_time = time.time()
    print(f"\nSuccessfully converted file to PGN with {len(games)} game(s) ({round(end_time - start_time, 3)}s).")
    return "\n\n".join(str(game) for game in games)

def decode_chunk(game):
    chess_board = chess.Board()
    move_binaries = []

    for move in game.mainline_moves():
        legal_move_ucis = [legal_move.uci() for legal_move in chess_board.legal_moves]
        if not legal_move_ucis:
            break
        move_binary = to_binary_string(legal_move_ucis.index(move.uci()), int(math.log2(len(legal_move_ucis))))
        chess_board.push(move)
        move_binaries.append(move_binary)

        st.session_state.move_count += 1

    st.session_state.game_count += 1
    return ''.join(move_binaries)

async def decode(pgn_string: str):
    start_time = time.time()
    games = get_pgn_games(pgn_string)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        binary_chunks = list(executor.map(decode_chunk, games))

    binary_data = ''.join(binary_chunks)
    byte_data = bytearray()

    for i in range(0, len(binary_data), 8):
        byte = binary_data[i:i+8]
        if len(byte) == 8:
            byte_data.append(int(byte, 2))

    end_time = time.time()
    print(f"\nSuccessfully decoded PGN with {len(games)} game(s) ({round(end_time - start_time, 3)}s).")
    return byte_data

def get_mime_type(file_name):
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type or "application/octet-stream"

# Main application
def main():
    st.title("Chess Steganography")

    # User authentication
    users = load_users()
    if st.session_state.user is None:
        st.subheader("Login or Register")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        col1, col2 = st.columns(2)
        if col1.button("Login"):
            if username in users and users[username] == hash_password(password):
                st.session_state.user = username
                user_data = load_user_data(username)
                st.session_state.encoded_files = user_data['encoded_files']
                st.session_state.decoded_files = user_data['decoded_files']
                st.success("Logged in successfully!")
            else:
                st.error("Invalid username or password")
        if col2.button("Register"):
            if username and password:
                if username not in users:
                    users[username] = hash_password(password)
                    save_users(users)
                    st.success("Registered successfully! You can now log in.")
                else:
                    st.error("Username already exists")
            else:
                st.error("Please enter a username and password")
    else:
        st.write(f"Logged in as: {st.session_state.user}")
        if st.button("Logout"):
            st.session_state.user = None
            st.session_state.encoded_files = []
            st.session_state.decoded_files = []
            st.experimental_rerun()

    if st.session_state.user:
        operation = st.radio("Choose operation", ["Encode", "Decode"])

        if operation == "Encode":
            uploaded_file = st.file_uploader("Choose a file to encode")  # Accepts any file type
            num_bots = st.slider("Speed of upload", min_value=10, max_value=500, value=20)

            if uploaded_file is not None:
                if st.button("Encode"):
                    st.session_state.move_count = 0
                    st.session_state.game_count = 0
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    with st.spinner("Encoding..."):
                        file_bytes = uploaded_file.getvalue()
                        pgn_output = asyncio.run(encode(file_bytes, num_bots))

                    encoded_data = {
                        "original_name": uploaded_file.name,
                        "mime_type": get_mime_type(uploaded_file.name),
                        "pgn_data": pgn_output,
                        "original_data": base64.b64encode(file_bytes).decode('utf-8')
                    }
                    st.session_state.encoded_files.append(encoded_data)
                    save_user_data(st.session_state.user, {
                        'encoded_files': st.session_state.encoded_files,
                        'decoded_files': st.session_state.decoded_files
                    })
                    st.success("Encoding complete!")

            # Real-time counter display
            if st.session_state.move_count > 0 or st.session_state.game_count > 0:
                st.write(f"Moves processed: {st.session_state.move_count}")
                st.write(f"Games created: {st.session_state.game_count}")

            if st.session_state.encoded_files:
                st.subheader("Encoded Files")
                for idx, file in enumerate(st.session_state.encoded_files):
                    st.write(f"{idx + 1}. {file['original_name']}")
                    col1, col2 = st.columns(2)
                    if col1.button(f"Download encoded PGN {idx + 1}"):
                        st.download_button(
                            label=f"Download {file['original_name']}.pgn",
                            data=file['pgn_data'],
                            file_name=f"{file['original_name']}.pgn",
                            mime="text/plain"
                        )
                    if col2.button(f"Download original file {idx + 1}"):
                        st.download_button(
                            label=f"Download {file['original_name']}",
                            data=base64.b64decode(file['original_data']),
                            file_name=file['original_name'],
                            mime=file['mime_type']
                        )

        elif operation == "Decode":
            uploaded_pgn = st.file_uploader("Choose a PGN file to decode", type=["pgn"])

            if uploaded_pgn is not None:
                if st.button("Decode"):
                    st.session_state.move_count = 0
                    st.session_state.game_count = 0
                    progress_bar = st.progress(0)
                    status_text = st.empty()
                    
                    with st.spinner("Decoding..."):
                        pgn_content = uploaded_pgn.getvalue().decode("utf-8")
                        decoded_data = asyncio.run(decode(pgn_content))

                    original_name = uploaded_pgn.name.rsplit('.', 1)[0]  # Remove .pgn extension
                    st.session_state.decoded_files.append({
                        "original_name": original_name,
                        "decoded_data": base64.b64encode(decoded_data).decode('utf-8'),
                        "mime_type": get_mime_type(original_name)
                    })
                    save_user_data(st.session_state.user, {
                        'encoded_files': st.session_state.encoded_files,
                        'decoded_files': st.session_state.decoded_files
                    })
                    st.success("Decoding complete!")

            # Real-time counter display
            if st.session_state.move_count > 0 or st.session_state.game_count > 0:
                st.write(f"Moves processed: {st.session_state.move_count}")
                st.write(f"Games processed: {st.session_state.game_count}")

            if st.session_state.decoded_files:
                st.subheader("Decoded Files")
                for idx, file in enumerate(st.session_state.decoded_files):
                    st.write(f"{idx + 1}. {file['original_name']}")
                    if st.button(f"Download decoded file {idx + 1}"):
                        st.download_button(
                            label=f"Download {file['original_name']}",
                            data=base64.b64decode(file['decoded_data']),
                            file_name=file['original_name'],
                            mime=file['mime_type']
                        )

if __name__ == "__main__":
    main()
