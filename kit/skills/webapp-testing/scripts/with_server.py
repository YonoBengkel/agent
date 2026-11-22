#!/usr/bin/env python3
"""
Start one or more servers, wait for them to be ready, run a command, then clean up.

Usage:
    # Single server
    python scripts/with_server.py --server "npm run dev" --port 5173 -- python automation.py
    python scripts/with_server.py --server "npm start" --port 3000 -- python test.py

    # Multiple servers
    python scripts/with_server.py \
      --server "cd backend && python server.py" --port 3000 \
      --server "cd frontend && npm run dev" --port 5173 \
      -- python test.py

Modified 2026-11-03 for the agent kit skill library (Apache-2.0 section 4b, see
SOURCE.md): stops each server's whole process tree, discards server output or writes it
to --log-dir instead of pipes nobody reads, refuses ports that are already taken, stops
waiting when a server exits early, and line-buffers its own output.
"""

import argparse
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path


def port_open(port):
    """True when something accepts connections on localhost:port."""
    try:
        with socket.create_connection(('localhost', port), timeout=1):
            return True
    except OSError:
        return False


def is_server_ready(port, process, timeout=30):
    """Wait for server to be ready by polling the port. Gives up early if the server exits."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if process.poll() is not None:
            return False
        if port_open(port):
            return True
        time.sleep(0.5)
    return False


def stop_tree(process):
    """Stop the shell and everything it started. terminate() alone kills only the shell,
    which on Windows leaves e.g. the node process behind `npm run dev` holding the port."""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/T', '/F', '/PID', str(process.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def main():
    # Keep these lines in order with the command's own output when stdout is a pipe
    sys.stdout.reconfigure(line_buffering=True)

    parser = argparse.ArgumentParser(description='Run command with one or more servers')
    parser.add_argument('--server', action='append', dest='servers', required=True, help='Server command (can be repeated)')
    parser.add_argument('--port', action='append', dest='ports', type=int, required=True, help='Port for each server (must match --server count)')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds per server (default: 30)')
    parser.add_argument('--log-dir', type=Path, help="Write each server's output to <log-dir>/server-<n>.log (default: discarded)")
    parser.add_argument('command', nargs=argparse.REMAINDER, help='Command to run after server(s) ready')

    args = parser.parse_args()

    # Remove the '--' separator if present
    if args.command and args.command[0] == '--':
        args.command = args.command[1:]

    if not args.command:
        print("Error: No command specified to run")
        sys.exit(1)

    # Parse server configurations
    if len(args.servers) != len(args.ports):
        print("Error: Number of --server and --port arguments must match")
        sys.exit(1)

    # A port that already answers belongs to another server: the readiness check would
    # pass at once and the command would test the wrong app.
    taken = [port for port in args.ports if port_open(port)]
    if taken:
        print(f"Error: port(s) already in use: {', '.join(map(str, taken))}. Pick free ports.")
        sys.exit(1)

    servers = []
    for cmd, port in zip(args.servers, args.ports):
        servers.append({'cmd': cmd, 'port': port})

    if args.log_dir:
        args.log_dir.mkdir(parents=True, exist_ok=True)

    server_processes = []
    log_files = []

    try:
        # Start all servers
        for i, server in enumerate(servers):
            print(f"Starting server {i+1}/{len(servers)}: {server['cmd']}")

            # Unread pipes fill up and block a chatty server, so output goes to a file or nowhere
            output = subprocess.DEVNULL
            if args.log_dir:
                output = open(args.log_dir / f'server-{i+1}.log', 'wb')
                log_files.append(output)

            # Use shell=True to support commands with cd and &&
            process = subprocess.Popen(
                server['cmd'],
                shell=True,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=(os.name != 'nt')
            )
            server_processes.append(process)

            # Wait for this server to be ready
            print(f"Waiting for server on port {server['port']}...")
            if not is_server_ready(server['port'], process, timeout=args.timeout):
                where = f"see {args.log_dir}" if args.log_dir else "rerun with --log-dir to see its output"
                raise RuntimeError(f"Server failed to start on port {server['port']} within {args.timeout}s ({where})")

            print(f"Server ready on port {server['port']}")

        print(f"\nAll {len(servers)} server(s) ready")

        # Run the command
        print(f"Running: {' '.join(args.command)}\n")
        result = subprocess.run(args.command)
        sys.exit(result.returncode)

    finally:
        # Clean up all servers
        print(f"\nStopping {len(server_processes)} server(s)...")
        for i, process in enumerate(server_processes):
            stop_tree(process)
            print(f"Server {i+1} stopped")
        for log_file in log_files:
            log_file.close()
        print("All servers stopped")


if __name__ == '__main__':
    main()
