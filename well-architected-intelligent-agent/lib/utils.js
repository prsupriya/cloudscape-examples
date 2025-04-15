"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Utils = void 0;
const fs = require("node:fs");
const path = require("node:path");
class Utils {
    static copyDirRecursive(sourceDir, targetDir) {
        if (!fs.existsSync(targetDir)) {
            fs.mkdirSync(targetDir);
        }
        const files = fs.readdirSync(sourceDir);
        for (const file of files) {
            const sourceFilePath = path.join(sourceDir, file);
            const targetFilePath = path.join(targetDir, file);
            const stats = fs.statSync(sourceFilePath);
            if (stats.isDirectory()) {
                Utils.copyDirRecursive(sourceFilePath, targetFilePath);
            }
            else {
                fs.copyFileSync(sourceFilePath, targetFilePath);
            }
        }
    }
}
exports.Utils = Utils;
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoidXRpbHMuanMiLCJzb3VyY2VSb290IjoiIiwic291cmNlcyI6WyJ1dGlscy50cyJdLCJuYW1lcyI6W10sIm1hcHBpbmdzIjoiOzs7QUFBQSw4QkFBOEI7QUFDOUIsa0NBQWtDO0FBRWxDLE1BQXNCLEtBQUs7SUFDekIsTUFBTSxDQUFDLGdCQUFnQixDQUFDLFNBQWlCLEVBQUUsU0FBaUI7UUFDMUQsSUFBSSxDQUFDLEVBQUUsQ0FBQyxVQUFVLENBQUMsU0FBUyxDQUFDLEVBQUUsQ0FBQztZQUM5QixFQUFFLENBQUMsU0FBUyxDQUFDLFNBQVMsQ0FBQyxDQUFDO1FBQzFCLENBQUM7UUFFRCxNQUFNLEtBQUssR0FBRyxFQUFFLENBQUMsV0FBVyxDQUFDLFNBQVMsQ0FBQyxDQUFDO1FBRXhDLEtBQUssTUFBTSxJQUFJLElBQUksS0FBSyxFQUFFLENBQUM7WUFDekIsTUFBTSxjQUFjLEdBQUcsSUFBSSxDQUFDLElBQUksQ0FBQyxTQUFTLEVBQUUsSUFBSSxDQUFDLENBQUM7WUFDbEQsTUFBTSxjQUFjLEdBQUcsSUFBSSxDQUFDLElBQUksQ0FBQyxTQUFTLEVBQUUsSUFBSSxDQUFDLENBQUM7WUFDbEQsTUFBTSxLQUFLLEdBQUcsRUFBRSxDQUFDLFFBQVEsQ0FBQyxjQUFjLENBQUMsQ0FBQztZQUUxQyxJQUFJLEtBQUssQ0FBQyxXQUFXLEVBQUUsRUFBRSxDQUFDO2dCQUN4QixLQUFLLENBQUMsZ0JBQWdCLENBQUMsY0FBYyxFQUFFLGNBQWMsQ0FBQyxDQUFDO1lBQ3pELENBQUM7aUJBQU0sQ0FBQztnQkFDTixFQUFFLENBQUMsWUFBWSxDQUFDLGNBQWMsRUFBRSxjQUFjLENBQUMsQ0FBQztZQUNsRCxDQUFDO1FBQ0gsQ0FBQztJQUNILENBQUM7Q0FDRjtBQXBCRCxzQkFvQkMiLCJzb3VyY2VzQ29udGVudCI6WyJpbXBvcnQgKiBhcyBmcyBmcm9tIFwibm9kZTpmc1wiO1xuaW1wb3J0ICogYXMgcGF0aCBmcm9tIFwibm9kZTpwYXRoXCI7XG5cbmV4cG9ydCBhYnN0cmFjdCBjbGFzcyBVdGlscyB7XG4gIHN0YXRpYyBjb3B5RGlyUmVjdXJzaXZlKHNvdXJjZURpcjogc3RyaW5nLCB0YXJnZXREaXI6IHN0cmluZyk6IHZvaWQge1xuICAgIGlmICghZnMuZXhpc3RzU3luYyh0YXJnZXREaXIpKSB7XG4gICAgICBmcy5ta2RpclN5bmModGFyZ2V0RGlyKTtcbiAgICB9XG5cbiAgICBjb25zdCBmaWxlcyA9IGZzLnJlYWRkaXJTeW5jKHNvdXJjZURpcik7XG5cbiAgICBmb3IgKGNvbnN0IGZpbGUgb2YgZmlsZXMpIHtcbiAgICAgIGNvbnN0IHNvdXJjZUZpbGVQYXRoID0gcGF0aC5qb2luKHNvdXJjZURpciwgZmlsZSk7XG4gICAgICBjb25zdCB0YXJnZXRGaWxlUGF0aCA9IHBhdGguam9pbih0YXJnZXREaXIsIGZpbGUpO1xuICAgICAgY29uc3Qgc3RhdHMgPSBmcy5zdGF0U3luYyhzb3VyY2VGaWxlUGF0aCk7XG5cbiAgICAgIGlmIChzdGF0cy5pc0RpcmVjdG9yeSgpKSB7XG4gICAgICAgIFV0aWxzLmNvcHlEaXJSZWN1cnNpdmUoc291cmNlRmlsZVBhdGgsIHRhcmdldEZpbGVQYXRoKTtcbiAgICAgIH0gZWxzZSB7XG4gICAgICAgIGZzLmNvcHlGaWxlU3luYyhzb3VyY2VGaWxlUGF0aCwgdGFyZ2V0RmlsZVBhdGgpO1xuICAgICAgfVxuICAgIH1cbiAgfVxufVxuIl19