# source env.sh — perfil floci só neste terminal (não mexe no ~/.aws)
_d="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export AWS_CONFIG_FILE="$_d/aws-config" AWS_SHARED_CREDENTIALS_FILE="$_d/aws-credentials" AWS_PROFILE=floci
[ -d "$_d/../cloud/tools/bin" ] && export PATH="$_d/../cloud/tools/bin:$PATH"   # AWS CLI local, se houver
[ -f "$_d/.venv/bin/activate" ] && source "$_d/.venv/bin/activate"
unset _d
