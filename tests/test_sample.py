"""src/sample.py — is_valid_domain() 的單元測試。"""
import pytest
from src.sample import is_valid_domain


@pytest.mark.parametrize('domain', [
    'example.com',
    'sub.example.com',
    'example.co.uk',
    'my-site.org',
    'a.io',
    'deep.sub.example.com',
    'xn--p1ai.ru',
])
def test_valid_domain(domain):
    assert is_valid_domain(domain) is True


@pytest.mark.parametrize('domain', [
    '',
    'example',
    '-example.com',
    'example.com.',
    'example..com',
    'http://example.com',
    'exam ple.com',
    '.com',
    'a',
    '123',
])
def test_invalid_domain(domain):
    assert is_valid_domain(domain) is False
