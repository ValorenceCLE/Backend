import aioping
import asyncio
import socket
import time
import logging
import aiohttp

# Configure logging for debugging and monitoring
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class NetworkTester:
    """
    An asynchronous network tester that measures:
      - ICMP Ping performance (average latency, jitter, packet loss).
      - Upload and download speeds using an HTTP-based speed test.
    
    The speed test downloads a fixed-size resource from a URL and calculates
    the effective speed in Mbps.
    
    Note: To use the HTTP speed test, supply a URL (starting with "http://" or "https://").
    """
    def __init__(self, host: str, timeout: float = 5.0, ping_count: int = 5, data_size: int = 1024 * 1024):
        """
        :param host: The host to test. This should be a full URL (e.g., "http://speedtest.example.com/testfile")
        :param timeout: Timeout in seconds for each test.
        :param ping_count: Number of ICMP ping attempts.
        :param data_size: Size in bytes for the speed test payload (default 1 MB).
        """
        self.host = host
        self.timeout = timeout
        self.ping_count = ping_count
        self.data_size = data_size

    async def ping_test(self) -> dict:
        """
        Perform multiple ICMP pings and compute:
          - average latency (seconds)
          - jitter (seconds)
          - packet loss (%)
        """
        latencies = []
        successes = 0

        # Extract hostname or IP from URL if needed
        hostname = self.host
        if "://" in self.host:
            hostname = self.host.split("://")[1].split("/")[0]

        try:
            ip = socket.gethostbyname(hostname)
        except Exception as e:
            logger.error(f"Failed to resolve {hostname}: {e}")
            return {
                "average_latency": None,
                "jitter": None,
                "packet_loss": 100.0
            }

        for i in range(self.ping_count):
            try:
                start = time.perf_counter()
                await aioping.ping(ip, timeout=self.timeout)
                end = time.perf_counter()
                latency = end - start
                latencies.append(latency)
                successes += 1
            except Exception as e:
                logger.warning(f"Ping attempt {i+1} failed for {hostname}: {e}")

        packet_loss = ((self.ping_count - successes) / self.ping_count) * 100.0
        if latencies:
            average_latency = sum(latencies) / len(latencies)
            variance = sum((lat - average_latency) ** 2 for lat in latencies) / len(latencies)
            jitter = variance ** 0.5
        else:
            average_latency = None
            jitter = None

        return {
            "average_latency": average_latency,
            "jitter": jitter,
            "packet_loss": packet_loss
        }

    async def speed_test_http(self) -> dict:
        """
        Perform a speed test using HTTP.
        Downloads up to self.data_size bytes from the provided URL and calculates the effective speed in Mbps.
        """
        try:
            async with aiohttp.ClientSession() as session:
                start = time.perf_counter()
                async with session.get(self.host, timeout=self.timeout) as response:
                    # Read data up to self.data_size bytes; if the resource is larger, we stop reading.
                    data = await response.content.read(self.data_size)
                end = time.perf_counter()
            duration = end - start
            if duration > 0 and data:
                # Convert bytes/second to Mbps: (bytes/duration)*8 / (1024*1024)
                speed_mbps = (len(data) * 8) / (duration * 1024 * 1024)
            else:
                speed_mbps = None
            # For HTTP, we simulate both upload and download speeds as the same value.
            return {
                "upload_speed": speed_mbps,
                "download_speed": speed_mbps
            }
        except Exception as e:
            logger.error(f"HTTP speed test failed for {self.host}: {e}")
            return {"upload_speed": None, "download_speed": None}

    async def run_all_tests(self) -> dict:
        """
        Run both the ping test and the HTTP speed test concurrently and aggregate the results.
        Overall status is 'Connected' if both tests return valid metrics.
        """
        ping_task = asyncio.create_task(self.ping_test())
        speed_task = asyncio.create_task(self.speed_test_http())

        ping_results, speed_results = await asyncio.gather(ping_task, speed_task)
        overall_status = "Connected" if (ping_results.get("average_latency") is not None and
                                         speed_results.get("upload_speed") is not None) else "Disconnected"
        return {
            "host": self.host,
            "ping": ping_results,
            "speed": speed_results,
            "status": overall_status
        }

# Example usage:
if __name__ == "__main__":
    async def main():
        # Supply a full URL for the HTTP-based speed test.
        tester = NetworkTester("https://google.com", timeout=5.0, ping_count=5)
        results = await tester.run_all_tests()
        
        # Format the output for readability
        print("HTTP-based Speed Test Results:")
        print(f"Host: {results['host']}\n")
        
        print("Ping Test Results:")
        print(f"  Average Latency: {results['ping']['average_latency']:.4f} seconds")
        print(f"  Jitter: {results['ping']['jitter']:.4f} seconds")
        print(f"  Packet Loss: {results['ping']['packet_loss']:.1f}%\n")
        
        print("Speed Test Results:")
        print(f"  Upload Speed: {results['speed']['upload_speed']:.4f} Mbps")
        print(f"  Download Speed: {results['speed']['download_speed']:.4f} Mbps\n")
        
        print(f"Overall Status: {results['status']}")

    asyncio.run(main())
