using System.IO;
using System.Text.RegularExpressions;

namespace WatchNetUi;

public static class Paths
{
    public static readonly string BarsDir = @"C:\QuikFinam\LuaScripts\barsSaver\data";
    public static readonly string NetDir = @"C:\QuikFinam\LuaIndicators\analyzer_net";
    public static readonly string MarksDir = @"C:\QuikFinam\LuaIndicators\analyzer_marks";

    public static string FindRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir != null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "analyzer", "__main__.py")))
                return dir.FullName;
            if (File.Exists(Path.Combine(dir.FullName, "pyproject.toml"))
                && Directory.Exists(Path.Combine(dir.FullName, "analyzer")))
                return dir.FullName;
            dir = dir.Parent;
        }

        // tools/WatchNetUi/WatchNetUi/bin/Debug/net8.0-windows → repo root = 5 levels up
        var fallback = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        if (Directory.Exists(Path.Combine(fallback, "analyzer")))
            return fallback;
        return Directory.GetCurrentDirectory();
    }
}

public static class InstrumentScanner
{
    private static readonly string[] NeedTfs = ["M1", "M10", "M30", "H4"];
    private static readonly Regex FileRe = new(
        @"^(?<sec>.+)_(?<cls>[A-Z0-9]+)_(?<tf>M1|M10|M30|H4|D1)_\.csv$",
        RegexOptions.Compiled | RegexOptions.CultureInvariant);

    public static IReadOnlyList<(string Sec, string ClassCode)> ListInstruments(string? barsDir = null)
    {
        var root = barsDir ?? Paths.BarsDir;
        if (!Directory.Exists(root))
            return Array.Empty<(string, string)>();

        var found = new Dictionary<(string, string), HashSet<string>>();
        foreach (var path in Directory.EnumerateFiles(root, "*.csv"))
        {
            var name = Path.GetFileName(path);
            var m = FileRe.Match(name);
            if (!m.Success) continue;
            var key = (m.Groups["sec"].Value, m.Groups["cls"].Value);
            if (!found.TryGetValue(key, out var set))
            {
                set = new HashSet<string>(StringComparer.Ordinal);
                found[key] = set;
            }
            set.Add(m.Groups["tf"].Value);
        }

        return found
            .Where(kv => NeedTfs.All(tf => kv.Value.Contains(tf)))
            .Select(kv => kv.Key)
            .OrderBy(k => k.Item1, StringComparer.OrdinalIgnoreCase)
            .ThenBy(k => k.Item2, StringComparer.OrdinalIgnoreCase)
            .ToList();
    }

    public static DateTime? FileWriteUtc(string path)
    {
        try
        {
            if (!File.Exists(path)) return null;
            return File.GetLastWriteTime(path);
        }
        catch
        {
            return null;
        }
    }

    public static string BarsM1Path(string sec, string classCode, string? barsDir = null)
        => Path.Combine(barsDir ?? Paths.BarsDir, $"{sec}_{classCode}_M1_.csv");

    public static string NetCsvPath(string sec, string classCode, string tf = "M10", string? netDir = null)
        => Path.Combine(netDir ?? Paths.NetDir, $"{sec}_{classCode}_{tf}.csv");

    public static DateTime? BestNetWrite(string sec, string classCode, string? netDir = null)
    {
        DateTime? best = null;
        foreach (var tf in new[] { "M1", "M10", "M30", "H4", "D1" })
        {
            var t = FileWriteUtc(NetCsvPath(sec, classCode, tf, netDir));
            if (t == null) continue;
            if (best == null || t > best) best = t;
        }
        return best;
    }

    public static string MarksCsvPath(string sec, string classCode, string tf = "M1", string? marksDir = null)
        => Path.Combine(marksDir ?? Paths.MarksDir, $"{sec}_{classCode}_{tf}.csv");

    public static DateTime? BestMarksWrite(string sec, string classCode, string? marksDir = null)
    {
        DateTime? best = null;
        foreach (var tf in new[] { "M1", "M10", "M30", "H4", "D1" })
        {
            var t = FileWriteUtc(MarksCsvPath(sec, classCode, tf, marksDir));
            if (t == null) continue;
            if (best == null || t > best) best = t;
        }
        return best;
    }
}
