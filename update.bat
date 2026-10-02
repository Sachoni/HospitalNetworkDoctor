@echo off
git add .
git commit -m "🔥 Add Comments"
git pull origin main --rebase
git push origin main
echo ✅ Update complete! Check your website in a few minutes. 🚀
pause
