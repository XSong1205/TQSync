import argparse
import os

def bump_version(part='patch'):
    version_file = os.path.join(os.path.dirname(__file__), '..', 'VERSION')
    
    try:
        with open(version_file, 'r', encoding='utf-8') as f:
            version_str = f.read().strip()
        
        parts = list(map(int, version_str.split('.')))
        if len(parts) != 3:
            raise ValueError("Invalid version format in VERSION file")
            
        major, minor, patch = parts
        
        if part == 'major':
            major += 1
            minor = 0
            patch = 0
        elif part == 'minor':
            minor += 1
            patch = 0
        elif part == 'patch':
            patch += 1
            
        new_version = f"{major}.{minor}.{patch}"
        
        with open(version_file, 'w', encoding='utf-8') as f:
            f.write(new_version + '\n')
            
        print(f"Version bumped to {new_version}")
        return new_version
        
    except Exception as e:
        print(f"Error bumping version: {e}")
        return None

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Bump project version')
    parser.add_argument('-a', action='store_true', dest='bump_major', help='Bump major version')
    parser.add_argument('-b', action='store_true', dest='bump_minor', help='Bump minor version')
    parser.add_argument('-c', action='store_true', dest='bump_patch', help='Bump patch version')
    
    args = parser.parse_args()
    
    if args.bump_major:
        bump_version('major')
    elif args.bump_minor:
        bump_version('minor')
    elif args.bump_patch:
        bump_version('patch')
    else:
        # Default to patch bump
        bump_version('patch')
