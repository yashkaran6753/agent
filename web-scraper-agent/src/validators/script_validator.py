import ast, asyncio, subprocess
from pathlib import Path
from loguru import logger

class ScriptValidator:
    @staticmethod
    def check_syntax(script_path: Path) -> tuple[bool, str]:
        try:
            ast.parse(script_path.read_text())
            return True, "Syntax OK"
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

    @staticmethod
    async def run_and_verify(script_path: Path, timeout: int = 60) -> tuple[bool, str]:
        """Run script and verify data was created."""
        logger.info("🧪 Testing script...")
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            output = stderr.decode() + stdout.decode()
            if proc.returncode != 0:
                return False, f"Runtime error: {output}"
            
            # Check data file exists
            data_files = list(Path("data").glob("*.json")) + list(Path("data").glob("*.csv"))
            if not data_files:
                return False, "No data files created"
            
            latest = max(data_files, key=lambda f: f.stat().st_mtime)
            if latest.stat().st_size < 10:
                return False, "Data file is empty"
                
            logger.success(f"✅ Script test passed – {latest.name}")
            return True, latest.read_text()
        except asyncio.TimeoutError:
            return False, "Script timed out after 60s"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}" 
import ast, asyncio, subprocess
from pathlib import Path
from loguru import logger

class ScriptValidator:
    @staticmethod
    def check_syntax(script_path: Path) -> tuple[bool, str]:
        try:
            ast.parse(script_path.read_text())
            return True, "Syntax OK"
        except SyntaxError as e:
            return False, f"Syntax error line {e.lineno}: {e.msg}"

    @staticmethod
    async def run_and_verify(script_path: Path, timeout: int = 60) -> tuple[bool, str]:
        """Run script and verify data was created."""
        logger.info("🧪 Testing script...")
        try:
            proc = await asyncio.create_subprocess_exec(
                "python", str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            
            if proc.returncode != 0:
                return False, f"Runtime error: {stderr.decode()}"
            
            data_files = list(Path("data").glob("*.json")) + list(Path("data").glob("*.csv"))
            if not data_files:
                return False, "No data files created"
            
            latest = max(data_files, key=lambda f: f.stat().st_mtime)
            if latest.stat().st_size < 10:
                return False, "Data file empty"
                
            logger.success(f"✅ Script test passed – {latest.name}")
            return True, latest.read_text()
        except asyncio.TimeoutError:
            return False, "Script timed out after 60s"