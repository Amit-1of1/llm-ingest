import json
import threading
import unittest
import urllib.error
import urllib.request

import llm_local_api


class LocalAPITests(unittest.TestCase):
    def _server(self, token=""):
        server = llm_local_api.create_server(
            llm_local_api.APIConfig(host="127.0.0.1", port=0, token=token)
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self._stop_server, server, thread)
        return server

    def _stop_server(self, server, thread):
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    def _url(self, server, path):
        host, port = server.server_address[:2]
        return f"http://{host}:{port}{path}"

    def test_health_endpoint_is_public(self):
        server = self._server()
        with urllib.request.urlopen(self._url(server, "/health"), timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["service"], "llm-ingest-api")

    def test_token_protects_post_endpoints(self):
        server = self._server(token="secret")
        request = urllib.request.Request(
            self._url(server, "/graph/query"),
            data=json.dumps({"index_dir": "x", "query": "test"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 401)
        caught.exception.close()

    def test_rejects_remote_bind_without_flag(self):
        with self.assertRaises(llm_local_api.APIError):
            llm_local_api.create_server(
                llm_local_api.APIConfig(host="0.0.0.0", port=0, allow_remote=False)
            )

    def test_openapi_payload_lists_core_endpoints(self):
        schema = llm_local_api._openapi_payload()
        self.assertIn("/convert", schema["paths"])
        self.assertIn("/graph/build", schema["paths"])
        self.assertIn("/graph/query", schema["paths"])


if __name__ == "__main__":
    unittest.main()
