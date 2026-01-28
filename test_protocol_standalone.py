"""
Unit tests for IO Board protocol encoding and decoding.

INSTALLATION:
1. Create 'tests' directory in project root
2. Move this file to tests/test_protocol.py
3. Install: pip install pytest pytest-asyncio
4. Run: pytest tests/test_protocol.py

Tests the binary protocol implementation including message building,
parsing, checksum calculation, and error handling.
"""

import pytest
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from io_board.protocol import (
    build_request,
    parse_response,
    calculate_checksum,
    STX,
    ETX,
)
from io_board.exceptions import ProtocolError, ErrorCode


class TestChecksumCalculation:
    """Test checksum calculation function."""
    
    def test_simple_checksum(self):
        """Test XOR checksum of simple data."""
        data = b"ABC"
        # A=0x41, B=0x42, C=0x43
        # 0x41 ^ 0x42 ^ 0x43 = 0x40
        expected = 0x40
        assert calculate_checksum(data) == expected
    
    def test_empty_checksum(self):
        """Test checksum of empty data."""
        assert calculate_checksum(b"") == 0
    
    def test_single_byte_checksum(self):
        """Test checksum of single byte."""
        assert calculate_checksum(b"\x42") == 0x42
    
    def test_known_protocol_checksum(self):
        """Test checksum with known protocol data."""
        # Command: MC, Subcommand: PD (Initialize)
        data = b"MCPD"
        checksum = calculate_checksum(data)
        assert isinstance(checksum, int)
        assert 0 <= checksum <= 255


class TestRequestBuilding:
    """Test protocol request message building."""
    
    def test_build_init_request(self):
        """Test building initialize (MCPD) request."""
        message = build_request("MC", "PD", {})
        
        # Check frame structure
        assert message[0:1] == STX
        assert message[1:3] == b"MC"
        assert message[3:5] == b"PD"
        assert message[-2:-1] == ETX
        
        # Check checksum is present
        assert len(message) == 7  # STX + MC + PD + ETX + checksum
    
    def test_build_door_control_open_request(self):
        """Test building door control OPEN request."""
        message = build_request("MC", "DC", {"DOOR": ord("O")})
        
        assert message[0:1] == STX
        assert message[1:3] == b"MC"
        assert message[3:5] == b"DC"
        assert message[5:6] == b"O"
        assert message[-2:-1] == ETX
    
    def test_build_door_control_close_request(self):
        """Test building door control CLOSE request."""
        message = build_request("MC", "DC", {"DOOR": ord("C")})
        
        assert message[0:1] == STX
        assert message[1:3] == b"MC"
        assert message[3:5] == b"DC"
        assert message[5:6] == b"C"
        assert message[-2:-1] == ETX
    
    def test_build_product_id_request(self):
        """Test building write product ID request."""
        product_id = "ABC12345678"
        message = build_request("MC", "WP", {"PRODUCT_ID": product_id})
        
        assert message[0:1] == STX
        assert message[1:3] == b"MC"
        assert message[3:5] == b"WP"
        assert message[5:16] == product_id.encode("ascii")
        assert message[-2:-1] == ETX
    
    def test_build_request_query_commands(self):
        """Test building various query (RQ) requests."""
        commands = [
            ("RQ", "MI", {}),  # Manufacturing info
            ("RQ", "IW", {}),  # Loadcells
            ("RQ", "ID", {}),  # IO status
            ("RQ", "ER", {}),  # Errors
        ]
        
        for cmd, subcmd, data in commands:
            message = build_request(cmd, subcmd, data)
            assert message[0:1] == STX
            assert message[1:3] == cmd.encode("ascii")
            assert message[3:5] == subcmd.encode("ascii")
            assert message[-2:-1] == ETX
    
    def test_build_request_invalid_command(self):
        """Test that invalid command raises ProtocolError."""
        with pytest.raises(ProtocolError) as exc_info:
            build_request("XX", "YY", {})
        
        assert exc_info.value.error_code == ErrorCode.PROTOCOL_BUILD_FAILED


class TestResponseParsing:
    """Test protocol response message parsing."""
    
    def test_parse_init_response(self):
        """Test parsing initialize (MCPD) response."""
        # Build valid response: STX + MC + PD + ETX + checksum
        data = b"MCPD"
        checksum = calculate_checksum(data + ETX)
        message = STX + data + ETX + bytes([checksum])
        
        response = parse_response(message)
        assert response.COMMAND == "MC"
        assert response.SUBCOMMAND == "PD"
    
    def test_parse_door_control_response(self):
        """Test parsing door control response."""
        # Response with door state OPEN
        data = b"MCDC" + b"O"
        checksum = calculate_checksum(data + ETX)
        message = STX + data + ETX + bytes([checksum])
        
        response = parse_response(message)
        assert response.COMMAND == "MC"
        assert response.SUBCOMMAND == "DC"
        assert response.DATA.DOOR == "OPEN"
    
    def test_parse_manufacturing_info_response(self):
        """Test parsing manufacturing info response."""
        product_id = "TEST1234567"
        sw_version = "01"
        data = b"RQMI" + product_id.encode("ascii") + sw_version.encode("ascii")
        checksum = calculate_checksum(data + ETX)
        message = STX + data + ETX + bytes([checksum])
        
        response = parse_response(message)
        assert response.COMMAND == "RQ"
        assert response.SUBCOMMAND == "MI"
        assert response.DATA.PRODUCT_ID == product_id
        assert response.DATA.SW_VERSION == sw_version
    
    def test_parse_loadcells_response(self):
        """Test parsing loadcell readings response."""
        # 10 loadcell readings of 6 chars each
        loadcells = ["+12345", "-00123", "+99999", "-12345", "+00000",
                     "-00001", "+54321", "-99999", "+11111", "-22222"]
        loadcells_bytes = "".join(loadcells).encode("ascii")
        data = b"RQIW" + loadcells_bytes
        checksum = calculate_checksum(data + ETX)
        message = STX + data + ETX + bytes([checksum])
        
        response = parse_response(message)
        assert response.COMMAND == "RQ"
        assert response.SUBCOMMAND == "IW"
        assert len(response.DATA.LOADCELLS) == 10
        for i, reading in enumerate(response.DATA.LOADCELLS):
            assert reading == loadcells[i]
    
    def test_parse_io_status_response(self):
        """Test parsing IO status response."""
        door = "OPENED"
        deadbolt = "CLOSED"
        data = b"RQID" + door.encode("ascii") + deadbolt.encode("ascii")
        checksum = calculate_checksum(data + ETX)
        message = STX + data + ETX + bytes([checksum])
        
        response = parse_response(message)
        assert response.COMMAND == "RQ"
        assert response.SUBCOMMAND == "ID"
        assert response.DATA.DOOR == door
        assert response.DATA.DEADBOLT == deadbolt
    
    def test_parse_errors_response(self):
        """Test parsing error list response."""
        errors = ["E001", "W002", "0000", "0000"]
        errors_bytes = "".join(errors).encode("ascii")
        data = b"RQER" + errors_bytes
        checksum = calculate_checksum(data + ETX)
        message = STX + data + ETX + bytes([checksum])
        
        response = parse_response(message)
        assert response.COMMAND == "RQ"
        assert response.SUBCOMMAND == "ER"
        assert len(response.DATA.ERRORS) == 4
        for i, error in enumerate(response.DATA.ERRORS):
            assert error == errors[i]
    
    def test_parse_invalid_checksum(self):
        """Test that invalid checksum raises ProtocolError."""
        data = b"MCPD"
        checksum = calculate_checksum(data + ETX)
        wrong_checksum = (checksum + 1) % 256
        message = STX + data + ETX + bytes([wrong_checksum])
        
        with pytest.raises(ProtocolError) as exc_info:
            parse_response(message)
        
        assert exc_info.value.error_code == ErrorCode.PROTOCOL_CHECKSUM_MISMATCH
    
    def test_parse_missing_stx(self):
        """Test that missing STX raises ProtocolError."""
        data = b"MCPD"
        checksum = calculate_checksum(data + ETX)
        message = data + ETX + bytes([checksum])  # Missing STX
        
        with pytest.raises(ProtocolError) as exc_info:
            parse_response(message)
        
        # Will fail during parsing
        assert exc_info.value.error_code in [
            ErrorCode.PROTOCOL_MALFORMED_DATA,
            ErrorCode.PROTOCOL_PARSE_FAILED
        ]
    
    def test_parse_missing_etx(self):
        """Test that missing ETX raises ProtocolError."""
        data = b"MCPD"
        checksum = calculate_checksum(data + ETX)
        message = STX + data + bytes([checksum])  # Missing ETX
        
        with pytest.raises(ProtocolError) as exc_info:
            parse_response(message)
        
        # Will fail during parsing
        assert exc_info.value.error_code in [
            ErrorCode.PROTOCOL_MALFORMED_DATA,
            ErrorCode.PROTOCOL_PARSE_FAILED
        ]
    
    def test_parse_truncated_message(self):
        """Test that truncated message raises ProtocolError."""
        message = STX + b"MC"  # Incomplete message
        
        with pytest.raises(ProtocolError) as exc_info:
            parse_response(message)
        
        assert exc_info.value.error_code in [
            ErrorCode.PROTOCOL_MALFORMED_DATA,
            ErrorCode.PROTOCOL_PARSE_FAILED
        ]


class TestRoundTrip:
    """Test request building and response parsing together."""
    
    def test_init_round_trip(self):
        """Test init command round trip."""
        # Build request
        request = build_request("MC", "PD", {})
        assert request[0:1] == STX
        
        # Simulate device echoing back same command
        data = b"MCPD"
        checksum = calculate_checksum(data + ETX)
        response_msg = STX + data + ETX + bytes([checksum])
        
        # Parse response
        response = parse_response(response_msg)
        assert response.COMMAND == "MC"
        assert response.SUBCOMMAND == "PD"
    
    def test_door_control_round_trip(self):
        """Test door control command round trip."""
        # Build OPEN request
        request = build_request("MC", "DC", {"DOOR": ord("O")})
        assert b"O" in request
        
        # Simulate device responding with OPEN state
        data = b"MCDCO"
        checksum = calculate_checksum(data + ETX)
        response_msg = STX + data + ETX + bytes([checksum])
        
        # Parse response
        response = parse_response(response_msg)
        assert response.COMMAND == "MC"
        assert response.SUBCOMMAND == "DC"
        assert response.DATA.DOOR == "OPEN"


if __name__ == "__main__":
    # Run tests if executed directly
    pytest.main([__file__, "-v"])
