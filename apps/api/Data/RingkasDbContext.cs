using Microsoft.AspNetCore.Identity.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore;

namespace Ringkas.Api.Data;

public sealed class RingkasDbContext(DbContextOptions<RingkasDbContext> options) : IdentityDbContext<ApplicationUser>(options);
