#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Agent 自动化爬取和运行工具
支持搜索、克隆和运行GitHub上的agent项目
"""

import os
import json
import subprocess
import requests
from requests.adapters import HTTPAdapter
try:
    from requests.packages.urllib3.util.retry import Retry
except ImportError:
    from urllib3.util.retry import Retry
import sys
import platform
from typing import List, Dict, Optional
from pathlib import Path
import time


class GitHubAgentAutomation:
    """GitHub Agent自动化类"""
    
    def __init__(self, github_token: Optional[str] = None, output_dir: str = "github_agents"):
        """
        初始化
        
        Args:
            github_token: GitHub API token (可选，但推荐使用以提高API限制)
            output_dir: 保存克隆项目的目录
        """
        self.github_token = github_token
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.headers = {
            "Accept": "application/vnd.github.v3+json"
        }
        if github_token:
            self.headers["Authorization"] = f"token {github_token}"
        
        # 创建带重试机制的 session
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # 配置重试策略
        retry_strategy = Retry(
            total=5,  # 总共重试5次
            backoff_factor=1,  # 重试间隔：1, 2, 4, 8, 16 秒
            status_forcelist=[429, 500, 502, 503, 504],  # 这些状态码会触发重试
            allowed_methods=["GET", "POST"]  # 允许重试的方法
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def search_agents(self, keyword: str = "agent", language: str = "python", 
                     sort: str = "stars", order: str = "desc", per_page: int = 10, 
                     page: int = 1) -> List[Dict]:
        """
        搜索GitHub上的agent项目
        
        Args:
            keyword: 搜索关键词
            language: 编程语言
            sort: 排序方式 (stars, forks, updated)
            order: 排序顺序 (desc, asc)
            per_page: 每页结果数量
            page: 页码（从1开始）
            
        Returns:
            项目列表
        """
        print(f"🔍 正在搜索GitHub上的 '{keyword}' 项目 (第 {page} 页)...")
        
        url = "https://api.github.com/search/repositories"
        params = {
            "q": f"{keyword} language:{language}",
            "sort": sort,
            "order": order,
            "per_page": per_page,
            "page": page
        }
        
        # 重试机制
        max_retries = 3
        retry_delay = 2  # 初始延迟2秒
        
        for attempt in range(max_retries):
            try:
                # 使用 session 发送请求，设置超时
                response = self.session.get(
                    url, 
                    params=params,
                    timeout=(10, 30),  # (连接超时, 读取超时)
                    verify=True  # 验证 SSL 证书
                )
                response.raise_for_status()  # 检查请求是否成功，失败则直接抛异常
                
                data = response.json()  # 将响应内容解析为JSON格式
                repositories = data.get("items", [])
                
                print(f"✅ 找到 {len(repositories)} 个项目")
                
                results = []
                for repo in repositories:
                    repo_info = {
                        "name": repo["name"],
                        "full_name": repo["full_name"],
                        "description": repo.get("description", ""),
                        "url": repo["html_url"],
                        "clone_url": repo["clone_url"],
                        "stars": repo["stargazers_count"],
                        "forks": repo["forks_count"],
                        "language": repo.get("language", ""),
                        "updated_at": repo["updated_at"]
                    }
                    results.append(repo_info)
                
                return results
                
            except requests.exceptions.SSLError as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # 指数退避
                    print(f"⚠️  SSL连接错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                    print(f"⏳ 等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ SSL连接失败，已重试 {max_retries} 次: {e}")
                    print("💡 提示: 可能是网络问题，请检查网络连接或稍后重试")
                    return []
                    
            except requests.exceptions.Timeout as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"⚠️  请求超时 (尝试 {attempt + 1}/{max_retries}): {e}")
                    print(f"⏳ 等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ 请求超时，已重试 {max_retries} 次: {e}")
                    return []
                    
            except requests.exceptions.ConnectionError as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"⚠️  连接错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                    print(f"⏳ 等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ 连接失败，已重试 {max_retries} 次: {e}")
                    print("💡 提示: 请检查网络连接")
                    return []
                    
            except requests.exceptions.HTTPError as e:
                # HTTP 错误（如 403, 404, 429 等）
                if e.response.status_code == 429:
                    # Rate limit exceeded
                    retry_after = int(e.response.headers.get('Retry-After', 60))
                    print(f"⚠️  API速率限制，等待 {retry_after} 秒...")
                    time.sleep(retry_after)
                    continue
                else:
                    print(f"❌ HTTP错误 ({e.response.status_code}): {e}")
                    return []
                    
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)
                    print(f"⚠️  请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                    print(f"⏳ 等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                else:
                    print(f"❌ 搜索失败，已重试 {max_retries} 次: {e}")
                    return []
        
        return []
    
    def is_repo_exists(self, repo_name: str) -> bool:
        """
        检查仓库是否已存在
        
        Args:
            repo_name: 仓库名称
            
        Returns:
            如果仓库目录存在返回True，否则返回False
        """
        repo_dir = self.output_dir / repo_name
        return repo_dir.exists()
    
    def clone_repository(self, clone_url: str, repo_name: str) -> bool:
        """
        克隆GitHub仓库
        
        Args:
            clone_url: 仓库克隆URL
            repo_name: 仓库名称
            
        Returns:
            是否成功
        """
        repo_dir = self.output_dir / repo_name
        
        if repo_dir.exists():
            print(f"⚠️  仓库 {repo_name} 已存在，跳过克隆")
            return True
        
        print(f"📥 正在克隆 {repo_name}...")
        
        try:
            subprocess.run(
                ["git", "clone", clone_url, str(repo_dir)],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"✅ 成功克隆 {repo_name}")
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"❌ 克隆失败 {repo_name}: {e.stderr}")
            return False
    
    def _get_venv_python(self, venv_path: Path) -> Path:
        """
        获取虚拟环境中的 Python 可执行文件路径
        
        Args:
            venv_path: 虚拟环境路径
            
        Returns:
            Python 可执行文件路径
        """
        if platform.system() == "Windows":
            return venv_path / "Scripts" / "python.exe"
        else:
            return venv_path / "bin" / "python"
    
    def _get_venv_pip(self, venv_path: Path) -> Path:
        """
        获取虚拟环境中的 pip 可执行文件路径
        
        Args:
            venv_path: 虚拟环境路径
            
        Returns:
            pip 可执行文件路径
        """
        if platform.system() == "Windows":
            return venv_path / "Scripts" / "pip.exe"
        else:
            return venv_path / "bin" / "pip"
    
    def create_venv(self, repo_path: Path) -> Optional[Path]:#可以返回虚拟环境路径，如果创建失败返回 None
        """
        为仓库创建独立的虚拟环境
        
        Args:
            repo_path: 项目路径
            
        Returns:
            虚拟环境路径，如果创建失败返回 None
        """
        venv_path = repo_path / "venv"
        
        # 如果虚拟环境已存在，检查是否有效
        if venv_path.exists():
            python_exe = self._get_venv_python(venv_path)
            if python_exe.exists():
                print(f"✅ 虚拟环境已存在: {venv_path}")
                return venv_path
            else:
                print(f"⚠️  虚拟环境不完整，重新创建...")
                import shutil
                shutil.rmtree(venv_path)
        
        print(f"🐍 正在创建虚拟环境: {venv_path}")
        
        try:
            # 使用 venv 模块创建虚拟环境
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)],
                check=True,
                capture_output=True,
                text=True
            )
            print(f"✅ 虚拟环境创建成功")
            return venv_path
            
        except subprocess.CalledProcessError as e:
            print(f"❌ 虚拟环境创建失败: {e.stderr}")
            return None
    
    def install_dependencies(self, repo_path: Path, use_venv: bool = True) -> bool:
        """
        安装项目依赖（在虚拟环境中）
        
        Args:
            repo_path: 项目路径
            use_venv: 是否使用虚拟环境（默认True）
            
        Returns:
            是否成功
        """
        print(f"📦 正在检查依赖文件...")
        
        # 创建或获取虚拟环境
        venv_path = None
        pip_cmd = ["pip"]
        python_cmd = ["python"]
        
        if use_venv:
            venv_path = self.create_venv(repo_path)
            if venv_path:
                pip_exe = self._get_venv_pip(venv_path)
                python_exe = self._get_venv_python(venv_path)
                if pip_exe.exists() and python_exe.exists():
                    pip_cmd = [str(pip_exe)]
                    python_cmd = [str(python_exe)]
                    print(f"📦 使用虚拟环境安装依赖: {venv_path}")
                else:
                    print(f"⚠️  虚拟环境不完整，使用系统 pip")
            else:
                print(f"⚠️  虚拟环境创建失败，使用系统 pip")
        
        # 检查requirements.txt
        requirements_file = repo_path / "requirements.txt"
        if requirements_file.exists():
            print(f"📦 找到 requirements.txt，正在安装依赖...")
            try:
                subprocess.run(
                    pip_cmd + ["install", "-r", str(requirements_file)],
                    check=True,
                    cwd=str(repo_path)
                )
                print(f"✅ 依赖安装成功")
                return True
            except subprocess.CalledProcessError as e:
                print(f"⚠️  依赖安装失败: {e}")
                return False
        
        # 检查setup.py
        setup_file = repo_path / "setup.py"
        if setup_file.exists():
            print(f"📦 找到 setup.py，正在安装...")
            try:
                subprocess.run(
                    pip_cmd + ["install", "-e", "."],
                    check=True,
                    cwd=str(repo_path)
                )
                print(f"✅ 安装成功")
                return True
            except subprocess.CalledProcessError as e:
                print(f"⚠️  安装失败: {e}")
                return False
        
        # 检查pyproject.toml
        pyproject_file = repo_path / "pyproject.toml"
        if pyproject_file.exists():
            print(f"📦 找到 pyproject.toml，正在安装...")
            try:
                subprocess.run(
                    pip_cmd + ["install", "-e", "."],
                    check=True,
                    cwd=str(repo_path)
                )
                print(f"✅ 安装成功")
                return True
            except subprocess.CalledProcessError as e:
                print(f"⚠️  安装失败: {e}")
                return False
        
        print(f"ℹ️  未找到依赖文件，跳过安装")
        return True
    
    def run_agent(self, repo_path: Path, run_command: Optional[str] = None, use_venv: bool = True) -> bool:
        """
        运行agent项目（在虚拟环境中）
        
        Args:
            repo_path: 项目路径
            run_command: 运行命令（如果为None，尝试自动检测）
            use_venv: 是否使用虚拟环境（默认True）
            
        Returns:
            是否成功
        """
        print(f"🚀 正在尝试运行agent...")
        
        # 获取 Python 命令
        python_cmd = ["python"]
        if use_venv:
            venv_path = repo_path / "venv"
            if venv_path.exists():
                python_exe = self._get_venv_python(venv_path)
                if python_exe.exists():
                    python_cmd = [str(python_exe)]
                    print(f"🐍 使用虚拟环境运行: {venv_path}")
        
        # 如果提供了运行命令，直接使用
        if run_command:
            try:
                cmd_parts = run_command.split()
                # 如果命令以 python 开头，替换为 venv 中的 python
                if cmd_parts[0] == "python" and use_venv:
                    cmd_parts[0] = python_cmd[0]
                subprocess.run(
                    cmd_parts,
                    check=True,
                    cwd=str(repo_path)
                )
                print(f"✅ 运行成功")
                return True
            except subprocess.CalledProcessError as e:
                print(f"❌ 运行失败: {e}")
                return False
        
        # 尝试自动检测运行方式
        # 检查是否有main.py
        main_file = repo_path / "main.py"
        if main_file.exists():
            print(f"📄 找到 main.py，正在运行...")
            try:
                subprocess.run(
                    python_cmd + ["main.py"],
                    check=True,
                    cwd=str(repo_path)
                )
                return True
            except subprocess.CalledProcessError as e:
                print(f"⚠️  运行失败: {e}")
        
        # 检查是否有app.py
        app_file = repo_path / "app.py"
        if app_file.exists():
            print(f"📄 找到 app.py，正在运行...")
            try:
                subprocess.run(
                    python_cmd + ["app.py"],
                    check=True,
                    cwd=str(repo_path)
                )
                return True
            except subprocess.CalledProcessError as e:
                print(f"⚠️  运行失败: {e}")
        
        # 检查README中的运行说明
        readme_file = repo_path / "README.md"
        if readme_file.exists():
            print(f"📖 请查看 README.md 了解如何运行此项目")
        
        return False
    
    def save_results(self, results: List[Dict], filename: str = "search_results.json"):
        """
        保存搜索结果到JSON文件
        
        Args:
            results: 搜索结果列表
            filename: 文件名
        """
        output_file = self.output_dir / filename
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"💾 结果已保存到 {output_file}")
    
    def process_agents(self, keyword: str = "agent", language: str = "python", 
                      clone: bool = True, install: bool = True, run: bool = False,
                      max_repos: int = 5, use_venv: bool = True):
        """
        完整的处理流程：搜索、克隆、安装、运行
        智能搜索：跳过已存在的仓库，继续搜索直到找到足够的新仓库
        
        Args:
            keyword: 搜索关键词
            language: 编程语言
            clone: 是否克隆仓库
            install: 是否安装依赖
            run: 是否运行项目
            max_repos: 需要处理的新仓库数量（默认5个）
            use_venv: 是否使用虚拟环境（默认True）
        """
        print(f"\n{'='*60}")
        print(f"🚀 开始智能搜索，目标：找到 {max_repos} 个新仓库")
        print(f"{'='*60}\n")
        
        # 智能搜索：跳过已存在的仓库，继续搜索直到找到足够的新仓库
        new_repos = []
        page = 1
        max_pages = 10  # 最多搜索10页，避免无限循环
        per_page = 30  # 每页搜索更多结果，提高效率
        
        while len(new_repos) < max_repos and page <= max_pages:
            # 搜索当前页
            search_results = self.search_agents(
                keyword=keyword, 
                language=language, 
                per_page=per_page,
                page=page
            )
            
            if not search_results:
                print(f"⚠️  第 {page} 页没有更多结果")
                break
            
            # 过滤掉已存在的仓库
            for repo in search_results:
                if not self.is_repo_exists(repo['name']):
                    new_repos.append(repo)
                    print(f"✅ 发现新仓库: {repo['full_name']} (已找到 {len(new_repos)}/{max_repos})")
                    
                    if len(new_repos) >= max_repos:
                        break
                else:
                    print(f"⏭️  跳过已存在仓库: {repo['full_name']}")
            
            # 如果还没找到足够的仓库，继续搜索下一页
            if len(new_repos) < max_repos:
                page += 1
                print(f"\n📄 继续搜索第 {page} 页...\n")
                time.sleep(1)  # 避免API限制
            else:
                break
        
        # 检查是否找到足够的仓库
        if not new_repos:
            print("❌ 未找到任何新仓库")
            return
        
        if len(new_repos) < max_repos:
            print(f"\n⚠️  只找到 {len(new_repos)} 个新仓库（目标: {max_repos}）")
        
        # 只取前 max_repos 个
        new_repos = new_repos[:max_repos]
        
        # 保存搜索结果
        self.save_results(new_repos, filename="new_repos_results.json")
        
        # 显示搜索结果
        print("\n" + "="*60)
        print("📋 将处理的新仓库列表:")
        print("="*60)
        for i, repo in enumerate(new_repos, 1):
            print(f"\n{i}. {repo['full_name']}")
            print(f"   ⭐ Stars: {repo['stars']} | 🍴 Forks: {repo['forks']}")
            print(f"   📝 {repo['description']}")
            print(f"   🔗 {repo['url']}")
        
        # 克隆和处理项目
        if clone:
            print("\n" + "="*60)
            print("📥 开始克隆和处理新仓库...")
            print("="*60)
            
            for repo in new_repos:
                print(f"\n{'='*60}")
                print(f"处理: {repo['full_name']}")
                print(f"{'='*60}")
                
                # 克隆
                if self.clone_repository(repo['clone_url'], repo['name']):
                    repo_path = self.output_dir / repo['name']
                    
                    # 安装依赖（在虚拟环境中）
                    if install:
                        self.install_dependencies(repo_path, use_venv=use_venv)
                    
                    # 运行项目（在虚拟环境中）
                    if run:
                        self.run_agent(repo_path, use_venv=use_venv)
                
                # 避免API限制
                time.sleep(1)
        
        print(f"\n✅ 完成！成功处理 {len(new_repos)} 个新仓库")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="GitHub Agent自动化爬取和运行工具")
    parser.add_argument("--keyword", "-k", default="agent", help="搜索关键词")
    parser.add_argument("--language", "-l", default="python", help="编程语言")
    parser.add_argument("--token", "-t", help="GitHub API Token (可选)")
    parser.add_argument("--output", "-o", default="github_agents", help="输出目录")
    parser.add_argument("--max", "-m", type=int, default=5, help="最大处理数量")
    parser.add_argument("--no-clone", action="store_true", help="不克隆仓库")
    parser.add_argument("--no-install", action="store_true", help="不安装依赖")
    parser.add_argument("--run", action="store_true", help="运行项目")
    parser.add_argument("--no-venv", action="store_true", help="不使用虚拟环境（默认使用venv隔离依赖）")
    
    args = parser.parse_args()
    
    # 创建自动化实例
    automation = GitHubAgentAutomation(
        github_token=args.token,
        output_dir=args.output
    )
    
    # 执行处理流程
    automation.process_agents(
        keyword=args.keyword,
        language=args.language,
        clone=not args.no_clone,
        install=not args.no_install,
        run=args.run,
        max_repos=args.max,
        use_venv=not args.no_venv
    )


if __name__ == "__main__":
    main()
