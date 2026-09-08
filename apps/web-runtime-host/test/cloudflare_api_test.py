#!/usr/bin/env python3
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import cloudflare_api as api

A = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
B = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
D = 'dddddddd-dddd-dddd-dddd-dddddddddddd'
E = 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee'


def deployment(identity=D, version=A):
    return {'deployments': [{'id': identity, 'versions': [{'version_id': version, 'percentage': 100}]}]}


class ClientTest(unittest.TestCase):
    def client(self, replies):
        client = api.CloudflareClient(token='test-secret', target='creator-web')
        requests = []
        def open_request(req, **kwargs):
            requests.append(req)
            self.assertEqual(kwargs['timeout'], 30)
            self.assertTrue(req.full_url.startswith('https://api.cloudflare.com/client/v4/accounts/' + api.ACCOUNT + '/workers/scripts/creator/'))
            value = replies.pop(0)
            if isinstance(value, Exception):
                raise value
            response = io.BytesIO(value if isinstance(value, bytes) else json.dumps({'success': True, 'result': value}).encode())
            response.status = 200
            response.geturl = lambda: req.full_url
            return response
        client._opener.open = open_request
        return client, requests

    def test_fixed_target_and_account_rejected_before_transport(self):
        for target, account in [('foreign', api.ACCOUNT), ('creator-web', 'foreign')]:
            with patch.object(api, 'build_opener') as opener, self.assertRaises(api.CloudflareError):
                api.CloudflareClient(token='secret', target=target, account=account)
            opener.assert_not_called()

    def test_single_version_state(self):
        client, _ = self.client([deployment()])
        self.assertEqual(client.deployment(), {'id': D, 'version_id': A})

    def test_empty_and_split_deployment_are_unusable(self):
        split = deployment(); split['deployments'][0]['versions'][0]['percentage'] = 50
        for value in ({'deployments': []}, split):
            client, _ = self.client([value])
            with self.assertRaises(api.CloudflareError): client.deployment()

    def test_publish_same_verified_version(self):
        client, requests = self.client([{'id': B}, deployment(), {'id': E}, deployment(E, B)])
        self.assertEqual(client.publish(version=B, expected_deployment=D), {'id': E, 'version_id': B})
        writes = [r for r in requests if r.data]
        self.assertEqual(len(writes), 1)
        self.assertEqual(json.loads(writes[0].data)['versions'], [{'version_id': B, 'percentage': 100}])

    def test_changed_deployment_stops_before_post(self):
        client, requests = self.client([{'id': B}, deployment(E)])
        with self.assertRaises(api.CloudflareError): client.publish(version=B, expected_deployment=D)
        self.assertFalse(any(r.data for r in requests))

    def test_missing_version_stops_before_post(self):
        client, requests = self.client([URLError('expired version and secret')])
        with self.assertRaises(api.CloudflareError) as caught: client.publish(version=B, expected_deployment=D)
        self.assertFalse(caught.exception.outcome_unknown)
        self.assertNotIn('secret', str(caught.exception))
        self.assertFalse(any(r.data for r in requests))

    def test_lost_mutation_receipt_is_unknown_and_not_retried(self):
        client, requests = self.client([{'id': B}, deployment(), URLError('test-secret')])
        with self.assertRaises(api.CloudflareError) as caught: client.publish(version=B, expected_deployment=D)
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertEqual(sum(bool(r.data) for r in requests), 1)
        self.assertNotIn('test-secret', str(caught.exception))

    def test_foreign_version_receipt_is_rejected(self):
        client, requests = self.client([{'id': A}])
        with self.assertRaises(api.CloudflareError): client.require_version(B)
        self.assertEqual(len(requests), 1)

    def test_route_disable_is_verified(self):
        client, _ = self.client([deployment(), {}, {'enabled': False, 'previews_enabled': True}, deployment()])
        self.assertEqual(client.set_route(enabled=False, expected_deployment=D), {'enabled': False, 'previews_enabled': True})

    def test_superseded_publication_is_unknown(self):
        client, _ = self.client([{'id': B}, deployment(), {'id': E}, deployment(E, A)])
        with self.assertRaises(api.CloudflareError) as caught: client.publish(version=B, expected_deployment=D)
        self.assertTrue(caught.exception.outcome_unknown)

    def test_response_size_limit(self):
        client, _ = self.client([b'x' * (api.MAX_RESPONSE + 1)])
        with self.assertRaises(api.CloudflareError): client.deployment()

    def test_redirect_does_not_forward_credentials(self):
        self.assertIsNone(api.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://foreign.example'))

    def test_path_traversal_is_rejected_before_request(self):
        client, requests = self.client([])
        with self.assertRaises(api.CloudflareError): client.require_version('../subdomain')
        self.assertEqual(requests, [])

    def test_same_version_from_another_deployment_is_not_our_receipt(self):
        client, requests = self.client([{'id': B}, deployment(), {'id': E}, deployment(D, B)])
        with self.assertRaises(api.CloudflareError) as caught:
            client.publish(version=B, expected_deployment=D)
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertEqual(sum(bool(r.data) for r in requests), 1)

    def test_missing_post_deployment_identity_is_unknown(self):
        client, requests = self.client([{'id': B}, deployment(), {}])
        with self.assertRaises(api.CloudflareError) as caught:
            client.publish(version=B, expected_deployment=D)
        self.assertTrue(caught.exception.outcome_unknown)
        self.assertEqual(len(requests), 3)


if __name__ == '__main__': unittest.main()
