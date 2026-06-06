using Microsoft.EntityFrameworkCore;

namespace Ringkas.Api.Data;

public sealed class RingkasDbContext(DbContextOptions<RingkasDbContext> options) : DbContext(options);
